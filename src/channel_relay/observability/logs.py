"""OTLP log export (§11).

Mirrors ``metrics.py``/``tracing.py``: a per-app ``LoggerProvider`` is built from settings and kept
on ``app.state`` (never set globally) so multiple app instances — e.g. in tests — don't fight over
the global provider. Logs are exported to the **same** OTLP/gRPC endpoint as metrics and traces
(``RELAY_OTLP_ENDPOINT``) so all three signals land in one Collector. Export attaches only when logs
are enabled (``RELAY_TELEMETRY_LOGS_ENABLED``, default on) *and* an endpoint is configured — so a
relay with no collector (and the test suite) never spawns an exporter that retries a dead endpoint.
The batch processor swallows export errors, so a down Collector never crashes or blocks the relay.

The Loguru → OTel bridge lives in ``logging.py``: ``configure_logging`` attaches an OTel
``LoggingHandler`` bound to this provider as an extra Loguru sink, in addition to the stderr JSON
sink (dual sink). Log records never carry bodies, PII, keys, or credentials (guardrails, §9).
"""

from __future__ import annotations

from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import SERVICE_NAME as OTEL_SERVICE_NAME
from opentelemetry.sdk.resources import SERVICE_VERSION, Resource

from channel_relay import __version__
from channel_relay.observability.metrics import SERVICE_NAME
from channel_relay.settings import Settings


def build_logger_provider(
    settings: Settings,
    log_processor: LogRecordProcessor | None = None,
) -> LoggerProvider:
    """Build a LoggerProvider.

    Tests inject a synchronous in-memory ``log_processor``. Production attaches an OTLP batch
    exporter only when logs are enabled *and* an endpoint is configured.
    """
    resource = Resource.create(
        {
            OTEL_SERVICE_NAME: SERVICE_NAME,
            SERVICE_VERSION: __version__,
        }
    )
    provider = LoggerProvider(resource=resource)
    if log_processor is not None:
        provider.add_log_record_processor(log_processor)
    elif settings.telemetry_logs_enabled and settings.otlp_endpoint:
        provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=settings.otlp_endpoint)))
    return provider
