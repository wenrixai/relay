"""Structured JSON logging via Loguru (§11).

Logs are emitted as JSON to stderr. Standard-library logging (including uvicorn) is
intercepted and routed through Loguru so all output shares one JSON format. Bodies, PII,
keys, and credentials are never logged — call sites must not pass them.

When an OTel ``LoggerProvider`` is supplied (``configure_logging(logger_provider=...)``), an OTel
``LoggingHandler`` bound to it is added as a **second** Loguru sink so records are also exported over
OTLP alongside metrics/traces (dual sink; the stderr JSON sink is always kept). The handler is added
only as a Loguru sink — not to the stdlib root logger — because the ``InterceptHandler`` already
funnels stdlib/uvicorn records into Loguru, so a single Loguru sink is the one bridge point and there
is no double emission.
"""

from __future__ import annotations

import logging
import sys
from types import FrameType

from loguru import logger
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler


class InterceptHandler(logging.Handler):
    """Route stdlib logging records into Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(*, debug: bool = False, logger_provider: LoggerProvider | None = None) -> None:
    """Configure Loguru JSON logging and intercept stdlib/uvicorn logs.

    When ``logger_provider`` is set, also export records over OTLP via an OTel ``LoggingHandler``
    bound to it (dual sink; the stderr JSON sink is retained regardless).

    Idempotent: safe to call more than once (e.g. per app factory in tests).
    """
    level = "DEBUG" if debug else "INFO"

    logger.remove()
    logger.add(sys.stderr, level=level, serialize=True, backtrace=False, diagnose=False)
    if logger_provider is not None:
        # ``format="{message}"`` keeps the OTLP record body as the bare message (severity, timestamp,
        # and Loguru's structured ``extra`` fields — hostname/channel/latency_ms/trace id — travel as
        # the OTel record's own fields/attributes, not baked into the body text).
        logger.add(LoggingHandler(logger_provider=logger_provider), level=level, format="{message}")

    # Route stdlib logging through Loguru (uvicorn, asyncio, etc.).
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        std = logging.getLogger(name)
        std.handlers = [InterceptHandler()]
        std.propagate = False
