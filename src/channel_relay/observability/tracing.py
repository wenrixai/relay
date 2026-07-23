"""In-process OpenTelemetry traces with OTLP export (§11).

Mirrors ``metrics.py``: a per-app ``TracerProvider`` is built from settings and kept on
``app.state`` (never set globally) so multiple app instances — e.g. in tests — don't fight
over the global provider. Tracing is **off by default** (``RELAY_TELEMETRY_TRACES_ENABLED``);
when enabled it exports to the shared OTLP/gRPC endpoint (``RELAY_OTLP_ENDPOINT``). Collector
failure must never crash the relay; the batch processor swallows export errors.

Span model — the important request path (§3.1):

- FastAPI server span (auto-instrumented; health probes excluded)
  - ``relay.forward`` — the whole forwarding pipeline for one relayed request
    - ``relay.authorize`` — stage [6] operation allow-list check
    - ``relay.request.credential_swap`` — stages [8a]/[8b] credential header/body injection
    - ``relay.request.pii`` — stage [7] ``ENC_`` token de-anonymization
    - ``relay.upstream`` — the httpx call to the channel (auto httpx CLIENT span nests inside)
    - ``relay.response.credential_swap`` — response credential cleanup/encryption
    - ``relay.response.pii`` — stage [9] PII redaction

Span attributes carry only non-sensitive scalars — channel name, operation name, status codes,
and the ``x-wenrix-trace-id`` correlation id (``wenrix.trace_id``). Bodies, headers,
credentials, and PII values must NEVER be recorded on spans (guardrails, §9).
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME as OTEL_SERVICE_NAME
from opentelemetry.sdk.resources import SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from channel_relay import __version__
from channel_relay.observability.metrics import SERVICE_NAME
from channel_relay.settings import Settings

TRACER_NAME = "channel_relay"

# One shared no-op tracer for the disabled path: spans are non-recording, attribute
# setting is a no-op, so a relay with tracing off pays (almost) nothing per request.
_NOOP_TRACER = trace.NoOpTracer()


def build_tracer_provider(
    settings: Settings,
    span_processor: SpanProcessor | None = None,
) -> TracerProvider:
    """Build a TracerProvider.

    Tests inject a synchronous in-memory ``span_processor``. Production attaches an OTLP
    batch exporter only when traces are enabled *and* an endpoint is configured — so a relay
    with no collector (and the test suite) never spawns an exporter that retries against a
    dead endpoint.
    """
    resource = Resource.create(
        {
            OTEL_SERVICE_NAME: SERVICE_NAME,
            SERVICE_VERSION: __version__,
        }
    )
    provider = TracerProvider(resource=resource)
    if span_processor is not None:
        provider.add_span_processor(span_processor)
    elif settings.telemetry_traces_enabled and settings.otlp_endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)))
    return provider


def tracer_from_provider(provider: TracerProvider | None) -> trace.Tracer:
    """The app's tracer, or the shared no-op tracer when tracing is disabled."""
    if provider is None:
        return _NOOP_TRACER
    return provider.get_tracer(TRACER_NAME)
