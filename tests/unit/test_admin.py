"""Tests for the authenticated admin diagnostics route."""

from __future__ import annotations

from typing import cast

import httpx
import pybase64
from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.settings import Settings

# pylint: disable=missing-function-docstring


def _basic(user: str, password: str) -> str:
    token = pybase64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


KEYRING_VALUE = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="
KEYRING_JSON = f'{{"0": "{KEYRING_VALUE}"}}'


def _admin_client(*, settings: Settings | None = None) -> TestClient:
    channel = ChannelConfig(
        name="sabre-prod",
        type=ChannelType.SABRE,
        host="sabre.example.test",
        proxy_pass="https://api-user:api-pass@sabre.example.test/v1",
        credentials={"enabled": True, "soap_security": "<Security>secret</Security>", "agency": "ABC123"},
        pii=ChannelPII(enabled=True),
    )
    app = create_app(
        config=RelayConfig(channels=[channel]),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    app.state.settings.basic_auth_enabled = True
    app.state.settings.basic_auth_user = "admin"
    app.state.settings.basic_auth_pass = "secret-pass"
    app.state.settings.otlp_endpoint = "https://otel.example.test:4317"
    app.state.settings.pii_keyring = KEYRING_JSON
    app.state.settings.pii_key_epoch_active = 0
    if settings is not None:
        app.state.settings = settings
    return TestClient(app)


def test_admin_flare_requires_basic_auth() -> None:
    with _admin_client() as client:
        missing = client.get("/admin/flare")
        wrong = client.get("/admin/flare", headers={"authorization": _basic("admin", "wrong")})

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"].startswith("Basic")
    assert wrong.status_code == 401


def test_admin_flare_fails_closed_when_basic_auth_disabled_or_incomplete() -> None:
    disabled = Settings(basic_auth_enabled=False, basic_auth_user="admin", basic_auth_pass="secret-pass")
    incomplete = Settings(basic_auth_enabled=True, basic_auth_user="admin", basic_auth_pass=None)

    with _admin_client(settings=disabled) as client:
        disabled_resp = client.get("/admin/flare", headers={"authorization": _basic("admin", "secret-pass")})
    with _admin_client(settings=incomplete) as client:
        incomplete_resp = client.get("/admin/flare", headers={"authorization": _basic("admin", "secret-pass")})

    assert disabled_resp.status_code == 401
    assert incomplete_resp.status_code == 401


def test_admin_flare_returns_redacted_diagnostics_snapshot() -> None:
    with _admin_client() as client:
        resp = client.get("/admin/flare", headers={"authorization": _basic("admin", "secret-pass")})

    assert resp.status_code == 200
    body = resp.json()
    assert body["runtime"]["hostname"]
    assert body["readiness"] == {"status": "ready", "reasons": []}
    assert body["settings"]["basic_auth"] == {"enabled": True, "configured": True}
    assert body["settings"]["otlp_endpoint_configured"] is True
    assert body["settings"]["pii_keyring_configured"] is True
    assert body["keyring"]["configured"] is True
    assert body["keyring"]["active_epoch"] == 0

    channel = body["channels"][0]
    assert channel["name"] == "sabre-prod"
    assert channel["type"] == "sabre"
    assert channel["host"] == "sabre.example.test"
    assert channel["proxy_pass"] == "https://sabre.example.test/v1"
    assert channel["credential_keys"] == ["agency", "soap_security"]
    assert channel["credential_count"] == 2
    assert channel["credential_swap_enabled"] is True
    assert channel["pii_enabled"] is True
    assert channel["authorization"] == {
        "enabled": False,
        "allowed_operations_count": 0,
        "external_configured": False,
    }

    serialized = resp.text
    assert "secret-pass" not in serialized
    assert "secret-key-material" not in serialized
    assert KEYRING_VALUE not in serialized
    assert "<Security>secret</Security>" not in serialized
    assert "ABC123" not in serialized
    assert "api-user" not in serialized
    assert "api-pass" not in serialized


def test_admin_flare_includes_in_process_statistics() -> None:
    client = _admin_client()
    app = cast(FastAPI, client.app)
    app.state.metrics.record_request("sabre-prod", 200)
    app.state.metrics.record_request("sabre-prod", 502)
    app.state.metrics.record_upstream_timeout("sabre-prod")
    app.state.metrics.record_upstream_error("sabre-prod")
    app.state.metrics.record_pii_redacted("sabre-prod", {"person": 2, "email": 1})
    app.state.metrics.record_pii_decrypted("sabre-prod", 3)
    app.state.metrics.record_xml_parse_error("sabre-prod", "invalid_xml")
    app.state.metrics.record_operation_denied("sabre-prod")
    app.state.metrics.record_uncovered_operation("sabre-prod", "PassengerDetailsRS")
    app.state.metrics.record_pii_rule_path_error("sabre-prod", "sabre.bad-prefix")

    with client:
        resp = client.get("/admin/flare", headers={"authorization": _basic("admin", "secret-pass")})

    assert resp.status_code == 200
    body = resp.json()
    assert body["statistics"] == {
        "channels_configured": 1,
        "rules_version": body["rules"]["rules_version"],
        "requests_total": {"sabre-prod": {"2xx": 1, "5xx": 1}},
        "upstream_timeouts_total": {"sabre-prod": 1},
        "upstream_errors_total": {"sabre-prod": 1},
        "pii_fields_redacted_total": {"sabre-prod": {"email": 1, "person": 2}},
        "pii_fields_decrypted_total": {"sabre-prod": 3},
        "xml_parse_errors_total": {"sabre-prod": {"invalid_xml": 1}},
        "operations_denied_total": {"sabre-prod": 1},
        "pii_uncovered_operation_total": {"sabre-prod": {"PassengerDetailsRS": 1}},
        "pii_rule_path_errors_total": {"sabre-prod": {"sabre.bad-prefix": 1}},
    }
