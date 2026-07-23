"""Tests for the configurable context path (RELAY_ROOT_PATH).

The relay serves all routes under a configured prefix, tolerant of both LB behaviors: whether the
prefix is forwarded (``/relay/channel/x``) or stripped by the LB (``/channel/x``). Empty root_path
keeps today's root-only routing.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.settings import Settings


def _ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200)


def _app_with_channel() -> Any:
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    return create_app(config=config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(_ok)))


def test_root_path_default_empty() -> None:
    assert Settings().root_path == ""


@pytest.mark.parametrize("raw", ["relay", "/relay", "/relay/", "relay/"])
def test_root_path_normalized(raw: str) -> None:
    assert Settings(root_path=raw).root_path == "/relay"


def test_prefixed_health_routes(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_ROOT_PATH", "/relay")
    with TestClient(create_app(config=RelayConfig())) as client:
        assert client.get("/relay/liveness").status_code == 200
        assert client.get("/relay/readiness").status_code == 200


def test_bare_routes_still_work_when_lb_strips(monkeypatch: Any) -> None:
    # If the LB strips the prefix, the relay receives the bare path — must still route.
    monkeypatch.setenv("RELAY_ROOT_PATH", "/relay")
    with TestClient(create_app(config=RelayConfig())) as client:
        assert client.get("/liveness").status_code == 200


def test_prefixed_channel_forwards(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_ROOT_PATH", "/relay")
    with TestClient(_app_with_channel()) as client:
        assert client.get("/relay/channel/tf/op").status_code == 200


def test_no_prefix_serves_root_only() -> None:
    with TestClient(create_app(config=RelayConfig())) as client:
        assert client.get("/liveness").status_code == 200
        assert client.get("/relay/liveness").status_code == 404
