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
    """``reason`` values for relay error responses (§10).

    Most are 502 (§10.3); ``OPERATION_NOT_ALLOWED`` is a 403 authorization rejection.
    """

    INTERNAL_ERROR = "internal_error"
    PII_REDACTION_FAILED = "pii_redaction_failed"
    PII_DEANONYMIZATION_FAILED = "pii_deanonymization_failed"
    XML_PARSE_ERROR = "xml_parse_error"
    CREDENTIAL_SWAP_FAILED = "credential_swap_failed"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"


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


def forbidden_operation_response(trace_id: str | None) -> Response:
    """403 JSON for an operation not permitted on a channel (§10, operation authorization).

    ``detail`` is fixed and carries no PII, credentials, or key material.
    """
    return JSONResponse(
        status_code=403,
        content={
            "error": "forbidden",
            "reason": ErrorReason.OPERATION_NOT_ALLOWED.value,
            "detail": "operation not allowed for this channel",
            "trace_id": trace_id,
        },
        headers={WENRIX_ERROR_HEADER: ErrorReason.OPERATION_NOT_ALLOWED.value},
    )


def payload_too_large_response() -> Response:
    """413 for an oversize inspectable body (§10.5)."""
    return JSONResponse(
        status_code=413,
        content={"error": "payload_too_large"},
        headers={WENRIX_ERROR_HEADER: "payload_too_large"},
    )


def unsupported_content_response(*, upstream: bool, trace_id: str | None) -> Response:
    """Fail closed when a body requiring structured inspection is not XML/SOAP."""
    status_code = 502 if upstream else 415
    error = "bad_gateway" if upstream else "unsupported_media_type"
    reason = ErrorReason.UNSUPPORTED_CONTENT_TYPE.value
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "reason": reason,
            "detail": "structured inspection supports XML and SOAP only",
            "trace_id": trace_id,
        },
        headers={WENRIX_ERROR_HEADER: reason},
    )
