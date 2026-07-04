"""Tests for the app skeleton: health probes and readiness reasons (T1.5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from channel_relay.config.models import RelayConfig
from channel_relay.health import readiness_reasons
from channel_relay.main import create_app


def test_liveness_ok(client: TestClient) -> None:
    resp = client.get("/liveness")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_readiness_ok(client: TestClient) -> None:
    resp = client.get("/readiness")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_readiness_reasons_empty_when_config_loaded() -> None:
    assert readiness_reasons(RelayConfig()) == []


def test_readiness_reasons_when_no_config() -> None:
    assert "config_not_loaded" in readiness_reasons(None)


def test_readiness_endpoint_not_ready() -> None:
    app = create_app(config=None)
    with TestClient(app, raise_server_exceptions=False) as _client:
        # Force not-ready state (lifespan may have loaded an empty config).
        app.state.config = None
        resp = _client.get("/readiness")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert "config_not_loaded" in body["reasons"]
