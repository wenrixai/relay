"""Upstream forwarding (pipeline stages [3]/[8]→[9], §3.1).

Resolves the request to a channel's upstream base and forwards it via httpx with
per-channel timeouts and **no retries** (§10.5). Header hygiene (§9.1) and the error
contract (§10) are layered on by their own stages.
"""

from __future__ import annotations

import gzip
import zlib

import httpx
from fastapi import Request
from loguru import logger
from starlette.responses import Response

from channel_relay.channels import get_handler
from channel_relay.channels.base import ChannelHandler, CredentialSwapError, SwapContext
from channel_relay.config.models import ChannelConfig, RelayConfig
from channel_relay.middleware.content import (
    ContentKind,
    body_exceeds_cap,
    classify_content,
    requires_inspection,
)
from channel_relay.middleware.header_hygiene import (
    clean_request_headers,
    clean_response_headers,
)
from channel_relay.observability.metrics import RelayMetrics
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import (
    DeanonymizationError,
    RedactionError,
    deanonymize_request_body,
    redact_response_body,
)
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import XmlOpsError, XmlOversizeError
from channel_relay.pii.xml_ops import parse_bytes, serialize
from channel_relay.proxy.errors import (
    TRACE_ID_HEADER,
    ErrorReason,
    internal_error_response,
    payload_too_large_response,
    upstream_timeout_response,
)

# Headers that become stale once the relay rewrites a body (recomputed downstream).
_BODY_SENSITIVE_HEADERS = frozenset({"content-length", "content-encoding"})


def _record_xml_error(metrics: RelayMetrics | None, channel: str, kind: str) -> None:
    if metrics is not None:
        metrics.record_xml_parse_error(channel, kind)


def find_channel(config: RelayConfig | None, name: str) -> ChannelConfig | None:
    """Return the channel with the given route name, or ``None`` if not configured."""
    if config is None:
        return None
    for channel in config.channels:
        if channel.name == name:
            return channel
    return None


def build_target_url(channel: ChannelConfig, path: str, query: str) -> httpx.URL:
    """Build the upstream URL from the channel base, remaining path, and query string."""
    base = (channel.proxy_pass or "").rstrip("/")
    url = f"{base}/{path}" if path else base
    if query:
        url = f"{url}?{query}"
    return httpx.URL(url)


def channel_timeout(channel: ChannelConfig) -> httpx.Timeout:
    """Per-channel connect/read timeout. No retries anywhere in the client."""
    return httpx.Timeout(
        connect=channel.timeouts.connect,
        read=channel.timeouts.read,
        write=channel.timeouts.read,
        pool=channel.timeouts.connect,
    )


def _headers_to_dict(headers: list[tuple[str, str]]) -> dict[str, str]:
    """Convert cleaned headers to a mutable mapping while preserving the last value."""
    return dict(headers)


def _remove_body_framing(headers: dict[str, str], *, remove_encoding: bool = False) -> None:
    """Remove stale body framing headers after a body rewrite."""
    for name in list(headers):
        lower = name.lower()
        if lower == "content-length" or (remove_encoding and lower == "content-encoding"):
            del headers[name]


def _gzip_decode(body: bytes) -> bytes:
    try:
        return gzip.decompress(body)
    except (zlib.error, OSError) as exc:
        raise CredentialSwapError("gzip request body could not be decoded") from exc


def _gzip_encode(body: bytes) -> bytes:
    return gzip.compress(body)


async def forward(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    client: httpx.AsyncClient,
    channel: ChannelConfig,
    path: str,
    request: Request,
    max_inspect_bytes: int,
) -> Response:
    # forward() orchestrates the pipeline stages (§3.1); each early return is one
    # contract-defined error shape, so the counts exceed pylint's generic budget.
    """Forward the incoming request to the channel and relay the response.

    Host is rewritten to the channel host (SNI follows the URL host). Full header hygiene
    is applied by the header-hygiene stage; this function keeps the raw body untouched.
    Non-XML/unknown and compressed bodies pass through unchanged; when this channel
    requires inspection, an oversize body is rejected with 413 (§5.4, §9.4).
    """
    trace_id = request.headers.get(TRACE_ID_HEADER)
    metrics: RelayMetrics | None = request.app.state.metrics
    if channel.proxy_pass is None:
        logger.bind(channel=channel.name).error("Channel has no upstream base configured")
        return internal_error_response(ErrorReason.INTERNAL_ERROR, "channel has no upstream configured", trace_id)

    body = await request.body()
    kind = classify_content(request.headers.get("content-type"))
    if requires_inspection(channel) and body_exceeds_cap(len(body), max_inspect_bytes):
        logger.bind(channel=channel.name, body_bytes=len(body)).warning("Inspectable body over cap")
        return payload_too_large_response()
    logger.bind(channel=channel.name, content_kind=kind).debug("Relaying body")
    url = build_target_url(channel, path, request.url.query)

    headers = _headers_to_dict(clean_request_headers(request.headers.items(), channel.host))
    keyring: Keyring | None = request.app.state.keyring
    handler = get_handler(channel.type)

    # [8a] Credential header injection needs no body and runs for every credentialed channel;
    # header-only channels (NDC) forward the body byte-for-byte (§spec: body left unchanged).
    if channel.credentials:
        header_outcome = _request_header_swap(handler, channel, headers, keyring, trace_id)
        if header_outcome is not None:
            return header_outcome

    # [7]/[8b] Body stages operate on decoded plaintext; gzip is decoded/re-encoded once here
    # so PII de-anonymization and credential-body swap never round-trip it twice.
    need_pii = channel.pii.enabled and keyring is not None and kind is ContentKind.XML
    need_cred_body = bool(channel.credentials) and handler.requires_body_inspection(channel)
    if body and (need_pii or need_cred_body):
        gzipped = request.headers.get("content-encoding", "").lower() == "gzip"
        try:
            working = _gzip_decode(body) if gzipped else body
        except CredentialSwapError:
            logger.bind(channel=channel.name).warning("Request body could not be gzip-decoded")
            return internal_error_response(ErrorReason.XML_PARSE_ERROR, "request body is not decodable", trace_id)
        changed = False
        # [7] De-anonymize: the channel must always receive plaintext (§8.6). Envelope-driven,
        # keyring-only; fail closed — an undecryptable token never reaches the channel.
        if need_pii and keyring is not None:
            pii_outcome = _request_pii_stage(
                channel=channel,
                keyring=keyring,
                body=working,
                max_inspect_bytes=max_inspect_bytes,
                trace_id=trace_id,
                metrics=metrics,
            )
            if isinstance(pii_outcome, Response):
                return pii_outcome
            working = pii_outcome
            changed = True
        if need_cred_body:
            swap_outcome = _request_credential_swap_stage(
                handler=handler,
                channel=channel,
                body=working,
                headers=headers,
                max_inspect_bytes=max_inspect_bytes,
                trace_id=trace_id,
                metrics=metrics,
                keyring=keyring,
            )
            if isinstance(swap_outcome, Response):
                return swap_outcome
            working, cred_changed = swap_outcome
            changed = changed or cred_changed
        if changed:
            body = _gzip_encode(working) if gzipped else working
            # The body changed size; stale framing headers must be recomputed by httpx.
            _remove_body_framing(headers)

    try:
        upstream = await client.request(
            request.method,
            url,
            headers=headers,
            content=body,
            timeout=channel_timeout(channel),
        )
    except httpx.TimeoutException:
        logger.bind(channel=channel.name).warning("Upstream timeout")
        if metrics is not None:
            metrics.record_upstream_timeout(channel.name)
        return upstream_timeout_response()
    except httpx.HTTPError:
        logger.bind(channel=channel.name).error("Upstream request failed")
        return internal_error_response(ErrorReason.INTERNAL_ERROR, "upstream request failed", trace_id)

    content = upstream.content
    response_headers = _headers_to_dict(clean_response_headers(upstream.headers.items()))
    response_kind = classify_content(upstream.headers.get("content-type"))

    if channel.credentials and content and response_kind is ContentKind.XML:
        response_swap_outcome = _response_credential_swap_stage(
            channel=channel,
            content=content,
            response_headers=response_headers,
            max_inspect_bytes=max_inspect_bytes,
            trace_id=trace_id,
            metrics=metrics,
            keyring=keyring,
        )
        if isinstance(response_swap_outcome, Response):
            return response_swap_outcome
        content, changed = response_swap_outcome
        if changed:
            _remove_body_framing(response_headers, remove_encoding=True)

    # [9] Redact: encrypt/mask PII fields per rules before the client sees them (§8.5).
    rules: RuleSet | None = request.app.state.rules
    if (
        channel.pii.enabled
        and keyring is not None
        and rules is not None
        and content
        and response_kind is ContentKind.XML
    ):
        redaction_outcome = _response_pii_stage(
            channel=channel,
            keyring=keyring,
            rules=rules,
            content=content,
            max_inspect_bytes=max_inspect_bytes,
            trace_id=trace_id,
            metrics=metrics,
        )
        if isinstance(redaction_outcome, Response):
            return redaction_outcome
        content = redaction_outcome
        # The relay rewrote the (decoded) body: framing headers are stale.
        for name in list(response_headers):
            if name.lower() in _BODY_SENSITIVE_HEADERS:
                del response_headers[name]

    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


def _request_header_swap(
    handler: ChannelHandler,
    channel: ChannelConfig,
    headers: dict[str, str],
    keyring: Keyring | None,
    trace_id: str | None,
) -> Response | None:
    """Pipeline stage [8a]: inject outbound credential headers; error → 502. No body needed."""
    try:
        handler.swap_request_headers(SwapContext(channel, headers, keyring))
    except CredentialSwapError:
        logger.bind(channel=channel.name).warning("Credential header swap failed")
        return internal_error_response(ErrorReason.CREDENTIAL_SWAP_FAILED, "request credential swap failed", trace_id)
    return None


def _request_credential_swap_stage(  # pylint: disable=too-many-arguments
    *,
    handler: ChannelHandler,
    channel: ChannelConfig,
    body: bytes,
    headers: dict[str, str],
    max_inspect_bytes: int,
    trace_id: str | None,
    metrics: RelayMetrics | None = None,
    keyring: Keyring | None = None,
) -> tuple[bytes, bool] | Response:
    """Pipeline stage [8b]: per-channel request *body* credential swap; error → 502.

    Only reached for handlers that require body inspection; ``body`` is already plaintext.
    """
    try:
        root = parse_bytes(body, max_bytes=max_inspect_bytes)
        changed = handler.swap_request_body(root, SwapContext(channel, headers, keyring))
        return (serialize(root), True) if changed else (body, False)
    except XmlOversizeError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        return payload_too_large_response()
    except XmlOpsError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        logger.bind(channel=channel.name).warning("Request XML rejected during credential swap")
        return internal_error_response(ErrorReason.XML_PARSE_ERROR, "request body is not parseable XML", trace_id)
    except CredentialSwapError:
        logger.bind(channel=channel.name).warning("Credential swap failed")
        return internal_error_response(
            ErrorReason.CREDENTIAL_SWAP_FAILED,
            "request credential swap failed",
            trace_id,
        )


def _response_credential_swap_stage(  # pylint: disable=too-many-arguments
    *,
    channel: ChannelConfig,
    content: bytes,
    response_headers: dict[str, str],
    max_inspect_bytes: int,
    trace_id: str | None,
    metrics: RelayMetrics | None = None,
    keyring: Keyring | None = None,
) -> tuple[bytes, bool] | Response:
    """Pipeline response hook: credential cleanup/encryption before PII redaction."""
    handler = get_handler(channel.type)
    try:
        root = parse_bytes(content, max_bytes=max_inspect_bytes)
        changed = handler.swap_response(root, SwapContext(channel, response_headers, keyring))
        return (serialize(root), True) if changed else (content, False)
    except XmlOversizeError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        return payload_too_large_response()
    except XmlOpsError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        logger.bind(channel=channel.name).warning("Response XML rejected during credential cleanup")
        return internal_error_response(ErrorReason.XML_PARSE_ERROR, "response body is not parseable XML", trace_id)
    except CredentialSwapError:
        logger.bind(channel=channel.name).warning("Response credential cleanup failed")
        return internal_error_response(
            ErrorReason.CREDENTIAL_SWAP_FAILED,
            "response credential cleanup failed",
            trace_id,
        )


def _request_pii_stage(  # pylint: disable=too-many-arguments
    *,
    channel: ChannelConfig,
    keyring: Keyring,
    body: bytes,
    max_inspect_bytes: int,
    trace_id: str | None,
    metrics: RelayMetrics | None = None,
) -> bytes | Response:
    """Pipeline stage [7]: de-anonymize the (plaintext) request body; error → contract Response."""
    try:
        working, decrypted = deanonymize_request_body(body, keyring=keyring, max_bytes=max_inspect_bytes)
    except XmlOversizeError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        return payload_too_large_response()
    except XmlOpsError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        logger.bind(channel=channel.name).warning("Request XML rejected by hardened parser")
        return internal_error_response(ErrorReason.XML_PARSE_ERROR, "request body is not parseable XML", trace_id)
    except DeanonymizationError:
        logger.bind(channel=channel.name).warning("De-anonymization failed")
        return internal_error_response(
            ErrorReason.PII_DEANONYMIZATION_FAILED,
            "request token de-anonymization failed",
            trace_id,
        )
    if decrypted:
        logger.bind(channel=channel.name, decrypted=decrypted).debug("De-anonymized tokens")
        if metrics is not None:
            metrics.record_pii_decrypted(channel.name, decrypted)
    return working


def _response_pii_stage(  # pylint: disable=too-many-arguments
    *,
    channel: ChannelConfig,
    keyring: Keyring,
    rules: RuleSet,
    content: bytes,
    max_inspect_bytes: int,
    trace_id: str | None,
    metrics: RelayMetrics | None = None,
) -> bytes | Response:
    """Pipeline stage [9]: redact the response body; error → contract Response."""
    try:
        # httpx already decoded any content-encoding, so `content` is plain XML.
        redacted, counts = redact_response_body(
            content,
            channel=(channel.type.value, channel.name),
            ruleset=rules,
            keyring=keyring,
            max_bytes=max_inspect_bytes,
            operation_parser=get_handler(channel.type).parse_operation,
        )
    except XmlOversizeError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        return payload_too_large_response()
    except XmlOpsError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        logger.bind(channel=channel.name).warning("Response XML rejected by hardened parser")
        return internal_error_response(ErrorReason.XML_PARSE_ERROR, "response body is not parseable XML", trace_id)
    except RedactionError:
        logger.bind(channel=channel.name).warning("PII redaction failed")
        return internal_error_response(ErrorReason.PII_REDACTION_FAILED, "response redaction failed", trace_id)
    if counts:
        logger.bind(channel=channel.name, counts=counts).debug("Redacted fields")
        if metrics is not None:
            metrics.record_pii_redacted(channel.name, counts)
    return redacted
