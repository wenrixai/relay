"""Tests for header hygiene (§9.1, T1.7)."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.middleware.header_hygiene import (
    clean_request_headers,
    clean_response_headers,
)


def _keys(pairs: list[tuple[str, str]]) -> set[str]:
    return {k.lower() for k, _ in pairs}


def test_clean_request_strips_hop_by_hop_and_forwarding() -> None:
    incoming = [
        ("host", "relay.local"),
        ("content-type", "text/xml"),
        ("connection", "keep-alive, x-custom"),
        ("keep-alive", "timeout=5"),
        ("transfer-encoding", "chunked"),
        ("x-forwarded-for", "1.2.3.4"),
        ("x-real-ip", "1.2.3.4"),
        ("forwarded", "for=1.2.3.4"),
        ("via", "1.1 proxy"),
        ("x-wenrix-trace-id", "abc"),
        ("proxy-authorization", "Basic zzz"),
        ("x-custom", "should-be-dropped-by-connection"),
    ]
    cleaned = clean_request_headers(incoming, "api.travelfusion.com")
    keys = _keys(cleaned)
    assert "content-type" in keys
    for gone in (
        "connection",
        "keep-alive",
        "transfer-encoding",
        "x-forwarded-for",
        "x-real-ip",
        "forwarded",
        "via",
        "x-wenrix-trace-id",
        "proxy-authorization",
        "x-custom",
    ):
        assert gone not in keys
    # Host rewritten to the channel host.
    host = [v for k, v in cleaned if k.lower() == "host"]
    assert host == ["api.travelfusion.com"]


def test_clean_request_strips_client_authorization() -> None:
    # The client Authorization header authenticates the client to the relay; it must never
    # reach a channel (§9.1). Only a credential-swap handler may set an outbound Authorization.
    incoming = [
        ("host", "relay.local"),
        ("content-type", "text/xml"),
        ("authorization", "Basic Y2xpZW50OnNlY3JldA=="),
        ("Authorization", "Basic mixedcase"),
    ]
    cleaned = clean_request_headers(incoming, "api.travelfusion.com")
    assert "authorization" not in _keys(cleaned)


def test_clean_response_strips_server_and_hop_by_hop() -> None:
    incoming = [
        ("server", "nginx"),
        ("content-type", "application/json"),
        ("connection", "close"),
        ("transfer-encoding", "chunked"),
        ("content-length", "123"),
        ("content-encoding", "gzip"),
    ]
    cleaned = clean_response_headers(incoming)
    keys = _keys(cleaned)
    assert "content-type" in keys
    for gone in ("server", "connection", "transfer-encoding", "content-length", "content-encoding"):
        assert gone not in keys


def _app_with_channel(handler: httpx.MockTransport) -> TestClient:
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    return TestClient(create_app(config=config, http_client=httpx.AsyncClient(transport=handler)))


def test_upstream_request_is_clean() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, headers={"server": "upstream"})

    with _app_with_channel(httpx.MockTransport(handler)) as client:
        resp = client.get(
            "/channel/tf/op",
            headers={
                "x-forwarded-for": "9.9.9.9",
                "x-wenrix-trace-id": "t1",
                "via": "1.1 x",
            },
        )

    req_headers = {k.lower() for k in captured["req"].headers}
    assert "x-forwarded-for" not in req_headers
    assert "x-wenrix-trace-id" not in req_headers
    assert "via" not in req_headers
    assert captured["req"].headers["host"] == "api.travelfusion.com"
    # No Server header reaches the client.
    assert "server" not in {k.lower() for k in resp.headers}


def test_client_authorization_not_forwarded_to_channel() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    # Travelfusion with no credentials = pass-through (no handler sets Authorization).
    with _app_with_channel(httpx.MockTransport(handler)) as client:
        client.get("/channel/tf/op", headers={"authorization": "Basic Y2xpZW50OnNlY3JldA=="})

    assert "authorization" not in {k.lower() for k in captured["req"].headers}


def test_no_server_header_on_health() -> None:
    with _app_with_channel(httpx.MockTransport(lambda r: httpx.Response(200))) as client:
        resp = client.get("/liveness")
    assert "server" not in {k.lower() for k in resp.headers}
