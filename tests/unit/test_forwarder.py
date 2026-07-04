"""Tests for routing + transparent pass-through forwarding (T1.6)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.proxy.forwarder import build_target_url, channel_timeout


def _app_with_channel(handler: httpx.MockTransport) -> TestClient:
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    mock_client = httpx.AsyncClient(transport=handler)
    return TestClient(create_app(config=config, http_client=mock_client))


def test_build_target_url_joins_base_path_query() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    url = build_target_url(channel, "CommandList", "x=1&y=2")
    assert str(url) == "https://api.travelfusion.com/CommandList?x=1&y=2"


def test_build_target_url_no_path() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    assert str(build_target_url(channel, "", "")) == "https://api.travelfusion.com"


def test_channel_timeout_uses_per_channel_values() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    channel.timeouts.connect = 5
    channel.timeouts.read = 7
    timeout = channel_timeout(channel)
    assert timeout.connect == 5
    assert timeout.read == 7


def test_forward_passes_method_path_query_body() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, content=b"upstream-body", headers={"x-test": "1"})

    with _app_with_channel(httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/CommandList?x=1",
            content=b"req-body",
            headers={"content-type": "text/xml"},
        )

    assert resp.status_code == 200
    assert resp.content == b"upstream-body"
    assert resp.headers["x-test"] == "1"
    req = captured["req"]
    assert req.method == "POST"
    assert str(req.url) == "https://api.travelfusion.com/CommandList?x=1"
    assert req.content == b"req-body"


def test_forward_rewrites_host_to_channel_host() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(204)

    with _app_with_channel(httpx.MockTransport(handler)) as client:
        client.get("/channel/tf/ping")

    assert captured["req"].headers["host"] == "api.travelfusion.com"


def test_unknown_channel_returns_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - not reached
        return httpx.Response(200)

    with _app_with_channel(httpx.MockTransport(handler)) as client:
        resp = client.get("/channel/nope/x")

    assert resp.status_code == 404


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "PATCH"])
def test_forward_supports_common_methods(method: str) -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    with _app_with_channel(httpx.MockTransport(handler)) as client:
        client.request(method, "/channel/tf/op")

    assert captured["req"].method == method
