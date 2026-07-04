"""Access logging (§11).

One structured JSON line per served channel request, with hostname, channel-endpoint
name, latency (measured on response receipt), and trace id. Never logs bodies or PII.
"""

from __future__ import annotations

import socket

from loguru import logger

_HOSTNAME = socket.gethostname()


def log_access(  # pylint: disable=too-many-arguments
    *,
    channel: str,
    method: str,
    path: str,
    status: int,
    latency_ms: float,
    trace_id: str | None,
) -> None:
    """Emit one access-log line for a served channel request."""
    logger.bind(
        hostname=_HOSTNAME,
        channel=channel,
        method=method,
        path=path,
        status=status,
        latency_ms=round(latency_ms, 3),
        trace_id=trace_id,
    ).info("channel request")
