"""Application entrypoint and factory.

The app factory wires the middleware pipeline (see ``openspec/specs/``). This slice boots
the app with health routes; feature stages are added per slice under TDD.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from starlette.responses import Response

from channel_relay import __version__
from channel_relay.admin import diagnostics_snapshot
from channel_relay.channels import credentials_require_response_keyring
from channel_relay.channels import get_handler
from channel_relay.config.loader import load_config
from channel_relay.config.models import RelayConfig
from channel_relay.health import readiness_reasons
from channel_relay.middleware.access_log import log_access
from channel_relay.middleware.auth import auth_active, verify_admin_basic_auth, verify_basic_auth
from channel_relay.middleware.context_path import ContextPathMiddleware
from channel_relay.observability.logging import configure_logging
from channel_relay.observability.logs import build_logger_provider
from channel_relay.observability.metrics import METER_NAME, RelayMetrics, build_meter_provider
from channel_relay.observability.tracing import build_tracer_provider
from channel_relay.pii.crypto import Keyring, load_keyring
from channel_relay.pii.rules_loader import load_rules
from channel_relay.proxy.forwarder import find_channel, forward
from channel_relay.settings import Settings

_RELAY_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


def client_limits(settings: Settings) -> httpx.Limits:
    """Build the upstream connection-pool limits from ``RELAY_*`` settings."""
    return httpx.Limits(
        max_connections=settings.max_connections,
        max_keepalive_connections=settings.max_keepalive_connections,
        keepalive_expiry=settings.keepalive_expiry,
    )


def build_http_client(settings: Settings, *, verify: bool = True) -> httpx.AsyncClient:
    """The shared upstream client: tuned pool, HTTP/1.1, connect-only retries (§10.5, D12).

    ``retries`` here retries a failed TCP/TLS *connection attempt* only (httpcore semantics);
    it never re-sends a request once bytes have gone out, so it cannot double-process an
    upstream operation. The relay still does not retry at the request level — that policy
    stays with the calling client.

    ``verify=False`` builds the second, insecure-TLS pool used only by channels that
    opt out of upstream certificate verification (`tls.insecure_skip_verify`).
    """
    transport = httpx.AsyncHTTPTransport(
        retries=settings.upstream_connect_retries, limits=client_limits(settings), verify=verify
    )
    return httpx.AsyncClient(transport=transport, verify=verify)


def build_keyring(settings: Settings, config: RelayConfig | None) -> Keyring | None:
    """Load the PII keyring; abort startup when PII is enabled without a valid one.

    Invalid keyring material raises regardless of PII flags (misconfiguration must be
    loud); a missing keyring raises only when some channel has ``pii.enabled`` and needs
    real encryption — a channel with ``pii.force_redact`` never encrypts, so it alone
    does not require a keyring (§8.3).
    """
    keyring = load_keyring(
        inline=settings.pii_keyring,
        file_path=settings.pii_keyring_file,
    )
    keyring_required = config is not None and any(
        (channel.pii.enabled and not channel.pii.force_redact) or credentials_require_response_keyring(channel)
        for channel in config.channels
    )
    if keyring is None and keyring_required:
        msg = "PII or response auth encryption is enabled for a channel but no keyring is configured"
        raise RuntimeError(msg)
    return keyring


def validate_auth_config(settings: Settings) -> None:
    """Abort startup when basic auth is enabled but no credentials are configured (§9.2).

    Fail closed: an enabled-but-unconfigured relay must refuse to boot rather than serve
    the data-plane routes open. Serving open is permitted only when basic auth is
    explicitly disabled (``basic_auth_enabled=False``).
    """
    if settings.basic_auth_enabled and not auth_active(settings):
        msg = (
            "basic auth is enabled but no credentials are configured "
            "(set RELAY_BASIC_AUTH_USER and RELAY_BASIC_AUTH_PASS, "
            "or disable auth with RELAY_BASIC_AUTH_ENABLED=false)"
        )
        raise RuntimeError(msg)


def validate_credential_config(config: RelayConfig | None) -> None:
    """Abort startup when a swap-enabled channel lacks the credentials its handler requires.

    Fail fast at config load rather than with a per-request 502: a channel that enables credential
    swap without configured auth would otherwise silently forward placeholder credentials.
    """
    if config is None:
        return
    for channel in config.channels:
        get_handler(channel.type).validate_credentials(channel)


def warn_unenforced_config(config: RelayConfig | None) -> None:
    """Warn loudly about accepted-but-unenforced config so operators are not silently unprotected.

    ``authorization.external`` is parsed and surfaced in diagnostics but the request
    pipeline does not call the external service in this version (§12.1, later phase).
    """
    if config is None:
        return
    for channel in config.channels:
        if channel.authorization.external is not None:
            logger.warning(
                "channel {channel!r}: authorization.external is configured but NOT enforced "
                "in this version; requests are not checked against the external service",
                channel=channel.name,
            )


def warn_insecure_tls_config(config: RelayConfig | None) -> None:
    """Warn loudly for every channel that disables upstream TLS certificate verification.

    `tls.insecure_skip_verify` is an explicit opt-out (default false); startup does not
    abort because of it, but every boot must surface which channels weakened transport
    security, matching `warn_unenforced_config`'s shape for `authorization.external`.
    """
    if config is None:
        return
    for channel in config.channels:
        if channel.tls.insecure_skip_verify:
            logger.warning(
                "channel {channel!r}: tls.insecure_skip_verify is enabled; upstream TLS "
                "server certificate verification is DISABLED for this channel",
                channel=channel.name,
            )


def _load_and_validate_startup_config(settings: Settings, application: FastAPI, metrics: RelayMetrics) -> None:
    """Load config once, then run its fail-closed checks and accepted-but-notable warnings.

    Missing file leaves ``application.state.config`` ``None`` (not-ready, §13.5); invalid
    config or a swap-enabled channel missing credentials raises to abort startup.
    """
    if application.state.config is None:
        application.state.config = _load_startup_config(settings)
    if application.state.config is not None:
        metrics.set_channels_configured(len(application.state.config.channels))
        validate_credential_config(application.state.config)
    warn_unenforced_config(application.state.config)
    warn_insecure_tls_config(application.state.config)


def _build_upstream_clients(settings: Settings, application: FastAPI) -> tuple[bool, bool]:
    """Build the shared client and, if some channel needs it, the insecure-TLS client.

    Returns ``(owns_client, owns_insecure_client)`` so the lifespan only closes what it
    created (an injected test client is never closed here).
    """
    owns_client = application.state.client is None
    if owns_client:
        application.state.client = build_http_client(settings)
    owns_insecure_client = application.state.insecure_client is None
    insecure_tls_required = application.state.config is not None and any(
        channel.tls.insecure_skip_verify for channel in application.state.config.channels
    )
    if owns_insecure_client and insecure_tls_required:
        application.state.insecure_client = build_http_client(settings, verify=False)
    return owns_client, owns_insecure_client


def _instrument_http_clients(
    application: FastAPI, meter_provider: MeterProvider, tracer_provider: TracerProvider | None
) -> None:
    """RED metrics (and, when tracing is enabled, client spans) via OTel auto-instrumentation,
    bound to this app's per-app providers (never the global ones, §11) so parallel app
    instances in tests don't cross-contaminate. Per-client, not global, for the same isolation
    reason; uninstrumented on teardown. A ``None`` tracer provider falls back to the global
    (no-op) tracer, so no spans are recorded when tracing is disabled."""
    HTTPXClientInstrumentor.instrument_client(
        application.state.client, meter_provider=meter_provider, tracer_provider=tracer_provider
    )
    if application.state.insecure_client is not None:
        HTTPXClientInstrumentor.instrument_client(
            application.state.insecure_client, meter_provider=meter_provider, tracer_provider=tracer_provider
        )


def _uninstrument_http_clients(application: FastAPI) -> None:
    if application.state.client is not None:
        HTTPXClientInstrumentor.uninstrument_client(application.state.client)
    if application.state.insecure_client is not None:
        HTTPXClientInstrumentor.uninstrument_client(application.state.insecure_client)


@dataclass(frozen=True)
class _Telemetry:
    """Per-app OTel providers and the single auto-instrumentation gate (built once per app)."""

    meter_provider: MeterProvider
    metrics: RelayMetrics
    tracer_provider: TracerProvider | None
    logger_provider: LoggerProvider | None
    instrument: bool


def _build_telemetry(
    settings: Settings,
    metric_reader: MetricReader | None,
    span_processor: SpanProcessor | None,
    log_processor: LogRecordProcessor | None,
) -> _Telemetry:
    """Build the per-app meter/tracer/logger providers from settings and test-injection hooks.

    Auto-instrumentation runs whenever any signal is collected — i.e. also when a test injects
    a ``metric_reader``/``span_processor`` without an OTLP endpoint; gate purely on the enable
    toggles. Traces are off by default (§11): with the flag off and no injected processor the
    tracer provider is never built, ``app.state.tracer_provider`` stays ``None``, and the
    pipeline uses a no-op tracer. Logs are on by default; the logger provider is built whenever
    logs are enabled (or a processor is injected), and only attaches an OTLP exporter when an
    endpoint is configured — otherwise ``app.state.logger_provider`` stays ``None``.
    """
    meter_provider = build_meter_provider(settings, reader=metric_reader)
    metrics = RelayMetrics(meter_provider.get_meter(METER_NAME))
    metrics_instrumentation = settings.telemetry_metrics_enabled or metric_reader is not None
    traces_instrumentation = settings.telemetry_traces_enabled or span_processor is not None
    tracer_provider = build_tracer_provider(settings, span_processor=span_processor) if traces_instrumentation else None
    logs_enabled = settings.telemetry_logs_enabled or log_processor is not None
    logger_provider = build_logger_provider(settings, log_processor=log_processor) if logs_enabled else None
    return _Telemetry(
        meter_provider=meter_provider,
        metrics=metrics,
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        instrument=metrics_instrumentation or traces_instrumentation,
    )


def _load_startup_config(settings: Settings) -> RelayConfig | None:
    """Load config on startup.

    Missing file → not ready (returns ``None``); invalid config → raise to abort startup.
    """
    if not Path(settings.config_file).exists():
        logger.bind(config_file=settings.config_file).warning("Config file not found; relay not ready")
        return None
    return load_config(settings.config_file)


# The app factory is intentionally wide: alongside config/clients it takes one in-memory
# test-injection hook per OTel signal (metrics/traces/logs) and wires the whole app in one place.
def create_app(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-statements
    config: RelayConfig | None = None,
    http_client: httpx.AsyncClient | None = None,
    insecure_http_client: httpx.AsyncClient | None = None,
    metric_reader: MetricReader | None = None,
    span_processor: SpanProcessor | None = None,
    log_processor: LogRecordProcessor | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    Args:
        config: an explicit config (used in tests). When omitted, the lifespan loads it
            from ``Settings.config_file``.
        http_client: an explicit httpx client (used in tests). When omitted, the lifespan
            creates and owns one.
        insecure_http_client: an explicit ``verify=False`` httpx client (used in tests) for
            channels with ``tls.insecure_skip_verify``. When omitted, the lifespan creates
            and owns one only if some configured channel needs it.
        metric_reader: an explicit metric reader (used in tests) to collect metrics in
            memory; production uses the OTLP periodic exporter.
        span_processor: an explicit span processor (used in tests) to collect spans in
            memory; production uses the OTLP batch exporter when tracing is enabled.
        log_processor: an explicit log-record processor (used in tests) to collect log records
            in memory; production uses the OTLP batch exporter when an endpoint is configured.

    ``server_header=False`` is enforced at the server level (uvicorn) per §9.1.
    """
    settings = Settings()
    # Build telemetry before logging so the OTel log sink can be wired into Loguru. The stderr
    # sink is present regardless, so errors raised before this point still surface.
    telemetry = _build_telemetry(settings, metric_reader, span_processor, log_processor)
    metrics = telemetry.metrics

    configure_logging(debug=settings.debug or settings.debug_mode, logger_provider=telemetry.logger_provider)
    if settings.debug_mode:
        logger.warning(
            "debug_mode is enabled: full (trimmed) request/response bodies will be logged at "
            "DEBUG level, including plaintext PII. Do not enable in production."
        )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Basic auth: enabled without credentials → abort (fail closed, §9.2).
        validate_auth_config(settings)
        _load_and_validate_startup_config(settings, application, metrics)
        # PII keyring: invalid → abort; missing while PII enabled → abort (§8.3).
        application.state.keyring = build_keyring(settings, application.state.config)
        owns_client, owns_insecure_client = _build_upstream_clients(settings, application)
        if telemetry.instrument:
            _instrument_http_clients(application, telemetry.meter_provider, telemetry.tracer_provider)
        # Rules: loaded once at startup from the baked bundle; no polling (§8.8, D7).
        pii_required = application.state.config is not None and any(
            channel.pii.enabled for channel in application.state.config.channels
        )
        application.state.rules = await load_rules(pii_required=pii_required)
        if application.state.rules is not None:
            metrics.set_rule_version(application.state.rules.rules_version)
        try:
            yield
        finally:
            if telemetry.instrument:
                _uninstrument_http_clients(application)
            if owns_client:
                await application.state.client.aclose()
            if owns_insecure_client and application.state.insecure_client is not None:
                await application.state.insecure_client.aclose()
            if telemetry.instrument:
                FastAPIInstrumentor.uninstrument_app(application)
            telemetry.meter_provider.shutdown()
            if telemetry.tracer_provider is not None:
                telemetry.tracer_provider.shutdown()
            if telemetry.logger_provider is not None:
                telemetry.logger_provider.shutdown()

    application = FastAPI(
        title="Wenrix Channel Relay",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    # Serve under a context path when configured; the middleware strips the prefix (if present) so
    # the root-mounted routes match whether or not the LB forwards it (§ relay-configuration).
    if settings.root_path:
        application.add_middleware(ContextPathMiddleware, root_path=settings.root_path)
    application.state.settings = settings
    application.state.config = config
    application.state.client = http_client
    application.state.insecure_client = insecure_http_client
    application.state.rules = None
    application.state.metrics = metrics
    application.state.meter_provider = telemetry.meter_provider
    application.state.tracer_provider = telemetry.tracer_provider
    application.state.logger_provider = telemetry.logger_provider
    application.state.started_at = time.time()
    # Server-side RED (http.server.request.duration) and, when tracing is enabled, the server
    # span. Health probes are excluded so k8s liveness/readiness traffic doesn't drown the
    # request histogram or the trace stream. Bound to the per-app providers; uninstrumented on
    # shutdown (see lifespan finally).
    if telemetry.instrument:
        FastAPIInstrumentor.instrument_app(
            application,
            meter_provider=telemetry.meter_provider,
            tracer_provider=telemetry.tracer_provider,
            excluded_urls="liveness,readiness",
        )

    @application.get("/liveness")
    async def liveness() -> dict[str, str]:
        """Liveness probe: the process is up."""
        return {"status": "alive"}

    @application.get("/readiness")
    async def readiness() -> JSONResponse:
        """Readiness probe: ready only when config has loaded; reasons otherwise (§13.5)."""
        reasons = readiness_reasons(application.state.config)
        if reasons:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reasons": reasons},
            )
        return JSONResponse(status_code=200, content={"status": "ready"})

    @application.get("/admin/flare", dependencies=[Depends(verify_admin_basic_auth)])
    async def admin_flare(request: Request) -> dict[str, object]:
        """Authenticated redacted diagnostics snapshot."""
        return diagnostics_snapshot(request)

    @application.api_route(
        "/channel/{name}",
        methods=_RELAY_METHODS,
        dependencies=[Depends(verify_basic_auth)],
    )
    @application.api_route(
        "/channel/{name}/{path:path}",
        methods=_RELAY_METHODS,
        dependencies=[Depends(verify_basic_auth)],
    )
    async def relay(name: str, request: Request, path: str = "") -> Response:
        """Route to a channel and forward transparently (§3.1, §5).

        Old nginx proxy allowed a bare ``/channel/<name>`` with no trailing path
        (e.g. Travelfusion); both route forms exist for that reason.
        """
        channel = find_channel(request.app.state.config, name)
        if channel is None:
            return JSONResponse(status_code=404, content={"error": "unknown_channel"})
        upstream_client = (
            request.app.state.insecure_client if channel.tls.insecure_skip_verify else request.app.state.client
        )
        start = time.perf_counter()
        response = await forward(
            upstream_client,
            channel,
            path,
            request,
            request.app.state.settings.max_inspect_bytes,
        )
        log_access(
            channel=name,
            method=request.method,
            path=path,
            status=response.status_code,
            latency_ms=(time.perf_counter() - start) * 1000,
            trace_id=request.headers.get("x-wenrix-trace-id"),
        )
        return response

    return application


app = create_app()


def cli() -> None:
    """Console entrypoint: run the relay with uvicorn (``server_header=False``).

    ``timeout_keep_alive`` must exceed the load balancer's idle timeout (AWS ALB defaults
    to 60s; the IaC pins 130s) or the LB reuses connections uvicorn has already closed →
    intermittent 502s. ``forwarded_allow_ips="*"`` is safe because deployment security
    groups/NetworkPolicies restrict ingress to the load balancer.

    ``loop``/``http`` are pinned to uvloop/httptools (declared runtime deps) so a resolver
    change that drops them fails loudly instead of silently degrading to asyncio/h11.
    """
    uvicorn.run(
        "channel_relay.main:app",
        host="0.0.0.0",  # relay binds all interfaces inside its container
        port=Settings().port,
        server_header=False,
        timeout_keep_alive=135,
        proxy_headers=True,
        forwarded_allow_ips="*",
        loop="uvloop",  # fail loud if the fast loop/parser is unavailable, not silent asyncio/h11
        http="httptools",
    )
