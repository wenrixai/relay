"""Error contract (§10).

Every relay-originated error is one of the shapes below. New relay errors use JSON; the
504 upstream-timeout stays text/html for v1 compatibility. All error responses omit
``Server`` (uvicorn ``server_header=False``) and carry ``X-Wenrix-Error``.
"""

from __future__ import annotations

from enum import StrEnum

from starlette.responses import HTMLResponse, JSONResponse, Response

WENRIX_ERROR_HEADER = "X-Wenrix-Error"
TRACE_ID_HEADER = "x-wenrix-trace-id"

_TIMEOUT_HTML = (
    "<!doctype html><html><head><title>Gateway Timeout</title></head>"
    "<body><h1>504 Gateway Timeout</h1><p>The upstream channel did not respond in time.</p>"
    "</body></html>"
)


class ErrorReason(StrEnum):
    """``reason`` values for 502 responses (§10.3)."""

    INTERNAL_ERROR = "internal_error"
    PII_REDACTION_FAILED = "pii_redaction_failed"
    PII_DEANONYMIZATION_FAILED = "pii_deanonymization_failed"
    XML_PARSE_ERROR = "xml_parse_error"
    CREDENTIAL_SWAP_FAILED = "credential_swap_failed"


def upstream_timeout_response() -> Response:
    """504 text/html + ``X-Wenrix-Error: upstream_timeout`` (§10.2)."""
    return HTMLResponse(
        status_code=504,
        content=_TIMEOUT_HTML,
        headers={WENRIX_ERROR_HEADER: "upstream_timeout"},
    )


def internal_error_response(
    reason: ErrorReason,
    detail: str,
    trace_id: str | None,
) -> Response:
    """502 JSON ``{error, reason, detail, trace_id}`` + ``X-Wenrix-Error`` (§10.3).

    ``detail`` must be human-readable and contain no PII.
    """
    return JSONResponse(
        status_code=502,
        content={
            "error": "bad_gateway",
            "reason": reason.value,
            "detail": detail,
            "trace_id": trace_id,
        },
        headers={WENRIX_ERROR_HEADER: reason.value},
    )


def payload_too_large_response() -> Response:
    """413 for an oversize inspectable body (§10.5)."""
    return JSONResponse(
        status_code=413,
        content={"error": "payload_too_large"},
        headers={WENRIX_ERROR_HEADER: "payload_too_large"},
    )
