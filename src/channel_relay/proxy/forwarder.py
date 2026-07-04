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


async def forward(  # pylint: disable=too-many-locals,too-many-return-statements
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
    metrics = getattr(request.app.state, "metrics", None)
    if channel.proxy_pass is None:
        logger.error("Channel {} has no upstream base configured", channel.name)
        return internal_error_response(ErrorReason.INTERNAL_ERROR, "channel has no upstream configured", trace_id)

    body = await request.body()
    kind = classify_content(request.headers.get("content-type"))
    if requires_inspection(channel) and body_exceeds_cap(len(body), max_inspect_bytes):
        logger.warning("Inspectable body over cap for channel {}: {} bytes", channel.name, len(body))
        return payload_too_large_response()
    logger.debug("Relaying {} body for channel {}", kind, channel.name)
    url = build_target_url(channel, path, request.url.query)

    headers = clean_request_headers(request.headers.items(), channel.host)

    # [7] De-anonymize: the channel must always receive plaintext (§8.6). Envelope-driven,
    # keyring-only; fail closed — an undecryptable token never reaches the channel.
    keyring = getattr(request.app.state, "keyring", None)
    if channel.pii.enabled and keyring is not None and body and kind is ContentKind.XML:
        outcome = _request_pii_stage(
            channel=channel,
            keyring=keyring,
            body=body,
            content_encoding=request.headers.get("content-encoding", "").lower(),
            max_inspect_bytes=max_inspect_bytes,
            trace_id=trace_id,
            metrics=metrics,
        )
        if isinstance(outcome, Response):
            return outcome
        body = outcome
        # The body changed size; stale framing headers must be recomputed by httpx.
        headers = [(k, v) for k, v in headers if k.lower() != "content-length"]

    try:
        upstream = await client.request(
            request.method,
            url,
            headers=headers,
            content=body,
            timeout=channel_timeout(channel),
        )
    except httpx.TimeoutException:
        logger.warning("Upstream timeout for channel {}", channel.name)
        if metrics is not None:
            metrics.record_upstream_timeout(channel.name)
        return upstream_timeout_response()
    except httpx.HTTPError:
        logger.error("Upstream request failed for channel {}", channel.name)
        return internal_error_response(ErrorReason.INTERNAL_ERROR, "upstream request failed", trace_id)

    content = upstream.content
    response_headers = clean_response_headers(upstream.headers.items())

    # [9] Redact: encrypt/mask PII fields per rules before the client sees them (§8.5).
    rules = getattr(request.app.state, "rules", None)
    response_kind = classify_content(upstream.headers.get("content-type"))
    if (
        channel.pii.enabled
        and keyring is not None
        and rules is not None
        and content
        and response_kind is ContentKind.XML
    ):
        outcome = _response_pii_stage(
            channel=channel,
            keyring=keyring,
            rules=rules,
            content=content,
            max_inspect_bytes=max_inspect_bytes,
            trace_id=trace_id,
            metrics=metrics,
        )
        if isinstance(outcome, Response):
            return outcome
        content = outcome
        # The relay rewrote the (decoded) body: framing headers are stale.
        response_headers = [(k, v) for k, v in response_headers if k.lower() not in _BODY_SENSITIVE_HEADERS]

    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=dict(response_headers),
    )


def _request_pii_stage(  # pylint: disable=too-many-arguments
    *,
    channel: ChannelConfig,
    keyring: Keyring,
    body: bytes,
    content_encoding: str,
    max_inspect_bytes: int,
    trace_id: str | None,
    metrics: RelayMetrics | None = None,
) -> bytes | Response:
    """Pipeline stage [7]: de-anonymize the request body; error → contract Response."""
    gzipped = content_encoding == "gzip"
    try:
        working = gzip.decompress(body) if gzipped else body
        working, decrypted = deanonymize_request_body(working, keyring=keyring, max_bytes=max_inspect_bytes)
        result = gzip.compress(working) if gzipped else working
    except XmlOversizeError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        return payload_too_large_response()
    except XmlOpsError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        logger.warning("Request XML rejected by hardened parser for channel {}", channel.name)
        return internal_error_response(ErrorReason.XML_PARSE_ERROR, "request body is not parseable XML", trace_id)
    except (DeanonymizationError, zlib.error, OSError):
        logger.warning("De-anonymization failed for channel {}", channel.name)
        return internal_error_response(
            ErrorReason.PII_DEANONYMIZATION_FAILED,
            "request token de-anonymization failed",
            trace_id,
        )
    if decrypted:
        logger.debug("De-anonymized {} tokens for channel {}", decrypted, channel.name)
        if metrics is not None:
            metrics.record_pii_decrypted(channel.name, decrypted)
    return result


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
            channel=channel.name,
            ruleset=rules,
            keyring=keyring,
            max_bytes=max_inspect_bytes,
        )
    except XmlOversizeError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        return payload_too_large_response()
    except XmlOpsError as exc:
        _record_xml_error(metrics, channel.name, exc.kind)
        logger.warning("Response XML rejected by hardened parser for channel {}", channel.name)
        return internal_error_response(ErrorReason.XML_PARSE_ERROR, "response body is not parseable XML", trace_id)
    except RedactionError:
        logger.warning("PII redaction failed for channel {}", channel.name)
        return internal_error_response(ErrorReason.PII_REDACTION_FAILED, "response redaction failed", trace_id)
    if counts:
        logger.debug("Redacted fields for channel {}: {}", channel.name, counts)
        if metrics is not None:
            metrics.record_pii_redacted(channel.name, counts)
    return redacted
