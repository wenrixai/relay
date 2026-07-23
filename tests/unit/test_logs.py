"""Tests for OTLP log export (§11): per-app LoggerProvider, gated on endpoint, dual sink.

Mirrors ``test_tracing.py``/``test_observability.py``: a per-app provider built from settings,
a test-injection hook (``log_processor``), OTLP export only when logs are enabled *and* an endpoint
is configured, and the stderr JSON sink retained alongside OTLP.
"""

from __future__ import annotations

import io
import json
import sys
from typing import Any

from loguru import logger
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor

from channel_relay import __version__
from channel_relay.config.models import RelayConfig
from channel_relay.main import create_app
from channel_relay.observability.logs import build_logger_provider
from channel_relay.observability.logging import configure_logging
from channel_relay.observability.metrics import SERVICE_NAME
from channel_relay.settings import Settings


def _processors(provider: LoggerProvider) -> list[Any]:
    return list(provider._multi_log_record_processor._log_record_processors)  # noqa: SLF001


def test_logger_provider_resource_has_service_identity() -> None:
    provider = build_logger_provider(Settings())
    assert provider.resource.attributes["service.name"] == SERVICE_NAME
    assert provider.resource.attributes["service.version"] == __version__


def test_no_otlp_exporter_without_endpoint() -> None:
    # Logs are enabled by default, but with no RELAY_OTLP_ENDPOINT no exporter is attached
    # (mirrors metrics/traces: never retry a dead collector, keep the suite exporter-free).
    provider = build_logger_provider(Settings())
    assert _processors(provider) == []


def test_otlp_exporter_attached_with_endpoint(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_OTLP_ENDPOINT", "localhost:4317")
    provider = build_logger_provider(Settings())
    assert len(_processors(provider)) == 1


def test_injected_processor_receives_records() -> None:
    exporter = InMemoryLogRecordExporter()
    create_app(config=RelayConfig(), log_processor=SimpleLogRecordProcessor(exporter))
    logger.info("relayed request", channel="tf")
    bodies = [data.log_record.body for data in exporter.get_finished_logs()]
    assert "relayed request" in bodies


def test_logs_disabled_yields_no_provider(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_TELEMETRY_LOGS_ENABLED", "false")
    app = create_app(config=RelayConfig())
    assert app.state.logger_provider is None


def test_dual_sink_keeps_stderr_and_adds_otlp(monkeypatch: Any) -> None:
    fake_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", fake_stderr)
    exporter = InMemoryLogRecordExporter()
    provider = build_logger_provider(Settings(), log_processor=SimpleLogRecordProcessor(exporter))

    configure_logging(logger_provider=provider)
    try:
        logger.info("dual sink line", channel="tf")
    finally:
        logger.remove()

    # stderr sink still emits structured JSON ...
    record = json.loads(fake_stderr.getvalue().strip().splitlines()[-1])
    assert record["record"]["message"] == "dual sink line"
    # ... and the same record reached the OTLP exporter.
    assert "dual sink line" in [data.log_record.body for data in exporter.get_finished_logs()]
