"""Tests for the error contract (§10, T1.9)."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.proxy.errors import (
    ErrorReason,
    internal_error_response,
    upstream_timeout_response,
)


def test_internal_error_response_shape() -> None:
    resp = internal_error_response(ErrorReason.INTERNAL_ERROR, "boom", "trace-123")
    assert resp.status_code == 502
    assert resp.headers["X-Wenrix-Error"] == "internal_error"


def test_upstream_timeout_response_shape() -> None:
    resp = upstream_timeout_response()
    assert resp.status_code == 504
    assert resp.headers["X-Wenrix-Error"] == "upstream_timeout"
    assert resp.media_type == "text/html"


def _client(channel: ChannelConfig, handler: httpx.MockTransport) -> TestClient:
    config = RelayConfig(channels=[channel])
    return TestClient(create_app(config=config, http_client=httpx.AsyncClient(transport=handler)))


def test_timeout_returns_504_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.get("/channel/tf/op")

    assert resp.status_code == 504
    assert resp.headers["x-wenrix-error"] == "upstream_timeout"
    assert resp.headers["content-type"].startswith("text/html")
    assert "server" not in {k.lower() for k in resp.headers}


def test_upstream_error_returns_502_json_with_trace_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.get("/channel/tf/op", headers={"x-wenrix-trace-id": "trace-xyz"})

    assert resp.status_code == 502
    body = resp.json()
    assert body["error"] == "bad_gateway"
    assert body["reason"] == "internal_error"
    assert body["trace_id"] == "trace-xyz"
    assert resp.headers["x-wenrix-error"] == "internal_error"


def test_no_upstream_configured_returns_502() -> None:
    # travelport has no default host -> proxy_pass is None
    channel = ChannelConfig(name="tp", type=ChannelType.TRAVELPORT)
    with _client(channel, httpx.MockTransport(lambda r: httpx.Response(200))) as client:
        resp = client.get("/channel/tp/op")

    assert resp.status_code == 502
    assert resp.headers["x-wenrix-error"] == "internal_error"
