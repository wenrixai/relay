"""Tests for the app skeleton: health probes and readiness reasons (T1.5)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_ok(client: TestClient) -> None:
    resp = client.get("/liveness")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_readiness_ok(client: TestClient) -> None:
    resp = client.get("/readiness")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_readiness_endpoint_not_ready(client: TestClient) -> None:
    client.app.state.config = None
    resp = client.get("/readiness")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert "config_not_loaded" in body["reasons"]
