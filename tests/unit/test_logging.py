"""Tests for structured JSON logging setup (T1.5)."""

from __future__ import annotations

import io
import json
import logging

from loguru import logger

from channel_relay.observability.logging import InterceptHandler, configure_logging


def test_configure_logging_intercepts_stdlib() -> None:
    configure_logging()
    root_handlers = logging.getLogger().handlers
    assert any(isinstance(h, InterceptHandler) for h in root_handlers)


def test_configure_logging_idempotent() -> None:
    configure_logging()
    configure_logging()  # must not raise or duplicate the stderr sink uncontrollably
    assert any(isinstance(h, InterceptHandler) for h in logging.getLogger().handlers)


def test_log_output_is_json_without_body() -> None:
    sink = io.StringIO()
    sink_id = logger.add(sink, serialize=True, level="INFO")
    try:
        logger.info("relayed request", channel="tf", latency_ms=12)
    finally:
        logger.remove(sink_id)
    record = json.loads(sink.getvalue().strip())
    assert record["record"]["message"] == "relayed request"
    assert "body" not in record["record"]["extra"]
    assert record["record"]["extra"]["channel"] == "tf"
