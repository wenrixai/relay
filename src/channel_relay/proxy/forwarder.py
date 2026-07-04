"""Upstream forwarding (pipeline stages [3]/[8]→[9], §3.1).

Resolves the request to a channel's upstream base and forwards it via httpx with
per-channel timeouts and **no retries** (§10.5). Header hygiene (§9.1) and the error
contract (§10) are layered on by their own stages.
"""

from __future__ import annotations

import httpx
from fastapi import Request
from loguru import logger
from starlette.responses import JSONResponse, Response

from channel_relay.config.models import ChannelConfig, RelayConfig
from channel_relay.middleware.content import (
    body_exceeds_cap,
    classify_content,
    requires_inspection,
)
from channel_relay.middleware.header_hygiene import (
    clean_request_headers,
    clean_response_headers,
)


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


async def forward(
    client: httpx.AsyncClient,
    channel: ChannelConfig,
    path: str,
    request: Request,
    max_inspect_bytes: int,
) -> Response:
    """Forward the incoming request to the channel and relay the response.

    Host is rewritten to the channel host (SNI follows the URL host). Full header hygiene
    is applied by the header-hygiene stage; this function keeps the raw body untouched.
    Non-XML/unknown and compressed bodies pass through unchanged; when this channel
    requires inspection, an oversize body is rejected with 413 (§5.4, §9.4).
    """
    body = await request.body()
    kind = classify_content(request.headers.get("content-type"))
    if requires_inspection(channel) and body_exceeds_cap(len(body), max_inspect_bytes):
        logger.warning("Inspectable body over cap for channel {}: {} bytes", channel.name, len(body))
        return JSONResponse(status_code=413, content={"error": "payload_too_large"})
    logger.debug("Relaying {} body for channel {}", kind, channel.name)
    url = build_target_url(channel, path, request.url.query)

    headers = clean_request_headers(request.headers.items(), channel.host)

    upstream = await client.request(
        request.method,
        url,
        headers=headers,
        content=body,
        timeout=channel_timeout(channel),
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(clean_response_headers(upstream.headers.items())),
    )
