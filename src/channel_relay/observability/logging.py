"""Structured JSON logging via Loguru (§11).

Logs are emitted as JSON to stderr. Standard-library logging (including uvicorn) is
intercepted and routed through Loguru so all output shares one JSON format. Bodies, PII,
keys, and credentials are never logged — call sites must not pass them.
"""

from __future__ import annotations

import logging
import sys
from types import FrameType

from loguru import logger


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


def configure_logging(*, debug: bool = False) -> None:
    """Configure Loguru JSON logging and intercept stdlib/uvicorn logs.

    Idempotent: safe to call more than once (e.g. per app factory in tests).
    """
    level = "DEBUG" if debug else "INFO"

    logger.remove()
    logger.add(sys.stderr, level=level, serialize=True, backtrace=False, diagnose=False)

    # Route stdlib logging through Loguru (uvicorn, asyncio, etc.).
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        std = logging.getLogger(name)
        std.handlers = [InterceptHandler()]
        std.propagate = False
