"""Smoke tests for the app skeleton (T1.5 fills in readiness reasons)."""

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
