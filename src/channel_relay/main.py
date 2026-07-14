"""Application entrypoint and factory.

The app factory wires the middleware pipeline (see ``openspec/specs/``). This slice boots
the app with health routes; feature stages are added per slice under TDD.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from opentelemetry.sdk.metrics.export import MetricReader
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
from channel_relay.observability.logging import configure_logging
from channel_relay.observability.metrics import METER_NAME, RelayMetrics, build_meter_provider
from channel_relay.pii.crypto import Keyring, load_keyring
from channel_relay.pii.rules_loader import load_rules
from channel_relay.proxy.forwarder import find_channel, forward
from channel_relay.settings import Settings

_RELAY_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


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
        active_epoch=settings.pii_key_epoch_active,
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


def _load_startup_config(settings: Settings) -> RelayConfig | None:
    """Load config on startup.

    Missing file → not ready (returns ``None``); invalid config → raise to abort startup.
    """
    if not Path(settings.config_file).exists():
        logger.bind(config_file=settings.config_file).warning("Config file not found; relay not ready")
        return None
    return load_config(settings.config_file)


def create_app(
    config: RelayConfig | None = None,
    http_client: httpx.AsyncClient | None = None,
    metric_reader: MetricReader | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    Args:
        config: an explicit config (used in tests). When omitted, the lifespan loads it
            from ``Settings.config_file``.
        http_client: an explicit httpx client (used in tests). When omitted, the lifespan
            creates and owns one.
        metric_reader: an explicit metric reader (used in tests) to collect metrics in
            memory; production uses the OTLP periodic exporter.

    ``server_header=False`` is enforced at the server level (uvicorn) per §9.1.
    """
    settings = Settings()
    configure_logging(debug=settings.debug)

    meter_provider = build_meter_provider(settings, reader=metric_reader)
    metrics = RelayMetrics(meter_provider.get_meter(METER_NAME))

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Basic auth: enabled without credentials → abort (fail closed, §9.2).
        validate_auth_config(settings)
        # Load config once on startup unless one was injected (invalid → abort).
        if application.state.config is None:
            application.state.config = _load_startup_config(settings)
        if application.state.config is not None:
            metrics.set_channels_configured(len(application.state.config.channels))
            # Credential swap enabled without configured auth → abort (fail closed at load).
            validate_credential_config(application.state.config)
        # Accepted-but-unenforced config (e.g. authorization.external) → loud warning.
        warn_unenforced_config(application.state.config)
        # PII keyring: invalid → abort; missing while PII enabled → abort (§8.3).
        application.state.keyring = build_keyring(settings, application.state.config)
        owns_client = application.state.client is None
        if owns_client:
            # No retries: the client owns retry policy, not the relay (§10.5, D12).
            application.state.client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0))
        # Rules: one startup fetch with baked fallback; no polling (§8.8, D7).
        pii_required = application.state.config is not None and any(
            channel.pii.enabled for channel in application.state.config.channels
        )
        application.state.rules = await load_rules(
            application.state.client,
            settings.rules_api_url,
            pii_required=pii_required,
        )
        if application.state.rules is not None:
            metrics.set_rule_version(application.state.rules.rules_version)
        try:
            yield
        finally:
            if owns_client:
                await application.state.client.aclose()
            meter_provider.shutdown()

    application = FastAPI(
        title="Wenrix Channel Relay",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.config = config
    application.state.client = http_client
    application.state.rules = None
    application.state.metrics = metrics
    application.state.meter_provider = meter_provider
    application.state.started_at = time.time()

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
        start = time.perf_counter()
        response = await forward(
            request.app.state.client,
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
    """
    uvicorn.run(
        "channel_relay.main:app",
        host="0.0.0.0",  # relay binds all interfaces inside its container
        port=Settings().port,
        server_header=False,
        timeout_keep_alive=75,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
