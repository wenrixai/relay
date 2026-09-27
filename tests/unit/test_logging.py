"""Tests for structured JSON logging setup (T1.5)."""

from __future__ import annotations

import logging

from channel_relay.observability.logging import InterceptHandler, configure_logging


def test_configure_logging_intercepts_stdlib() -> None:
    configure_logging()
    root_handlers = logging.getLogger().handlers
    assert any(isinstance(h, InterceptHandler) for h in root_handlers)
