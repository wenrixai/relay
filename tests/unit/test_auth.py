"""Tests for client basic authentication (§9.2, T1.10)."""

from __future__ import annotations

import base64

import httpx
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.middleware.auth import (
    auth_active,
    credentials_valid,
    parse_basic_credentials,
)
from channel_relay.settings import Settings


def _basic(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def test_parse_basic_credentials() -> None:
    assert parse_basic_credentials(_basic("u", "p")) == ("u", "p")
    assert parse_basic_credentials(None) is None
    assert parse_basic_credentials("Bearer xyz") is None
    assert parse_basic_credentials("Basic !!!not-base64") is None


def test_auth_active_requires_configured_credentials() -> None:
    assert auth_active(Settings(basic_auth_enabled=True)) is False
    assert auth_active(Settings(basic_auth_enabled=True, basic_auth_user="u", basic_auth_pass="p")) is True
    assert auth_active(Settings(basic_auth_enabled=False, basic_auth_user="u", basic_auth_pass="p")) is False


def test_credentials_valid() -> None:
    settings = Settings(basic_auth_user="u", basic_auth_pass="p")
    assert credentials_valid("u", "p", settings) is True
    assert credentials_valid("u", "wrong", settings) is False
    assert credentials_valid("wrong", "p", settings) is False


def _client(*, user: str | None = None, password: str | None = None) -> TestClient:
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    handler = httpx.MockTransport(lambda r: httpx.Response(200, content=b"ok"))
    app = create_app(config=config, http_client=httpx.AsyncClient(transport=handler))
    app.state.settings.basic_auth_enabled = True
    app.state.settings.basic_auth_user = user
    app.state.settings.basic_auth_pass = password
    return TestClient(app)


def test_missing_credentials_rejected() -> None:
    with _client(user="u", password="p") as client:
        resp = client.get("/channel/tf/op")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Basic")


def test_wrong_credentials_rejected() -> None:
    with _client(user="u", password="p") as client:
        resp = client.get("/channel/tf/op", headers={"authorization": _basic("u", "nope")})
    assert resp.status_code == 401


def test_valid_credentials_pass() -> None:
    with _client(user="u", password="p") as client:
        resp = client.get("/channel/tf/op", headers={"authorization": _basic("u", "p")})
    assert resp.status_code == 200
    assert resp.content == b"ok"


def test_probes_open_when_auth_enabled() -> None:
    with _client(user="u", password="p") as client:
        assert client.get("/liveness").status_code == 200
        assert client.get("/readiness").status_code == 200


def test_auth_disabled_serves_open() -> None:
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    handler = httpx.MockTransport(lambda r: httpx.Response(200))
    app = create_app(config=config, http_client=httpx.AsyncClient(transport=handler))
    app.state.settings.basic_auth_enabled = False
    with TestClient(app) as client:
        assert client.get("/channel/tf/op").status_code == 200
