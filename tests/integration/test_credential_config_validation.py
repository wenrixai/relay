"""Config-load validation: a swap-enabled SOAP channel must have configured credentials.

The relay fails fast at startup rather than forwarding placeholder credentials on the first request.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app

KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'


def _app(channel: ChannelConfig, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    monkeypatch.delenv("RELAY_RULES_API_URL", raising=False)
    return TestClient(
        create_app(
            config=RelayConfig(channels=[channel]),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200))),
        )
    )


def test_swap_enabled_soap_channel_without_credentials_aborts_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = ChannelConfig(name="sabre", type=ChannelType.SABRE, host="sabre.test", credentials={"enabled": True})
    with pytest.raises(ValueError, match="exactly one"):  # noqa: PT012 - error raised on lifespan enter
        with _app(channel, monkeypatch) as client:
            client.get("/liveness")


def test_swap_enabled_soap_channel_with_credentials_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = ChannelConfig(
        name="sabre",
        type=ChannelType.SABRE,
        host="sabre.test",
        credentials={"enabled": True, "soap_security": "<Security/>"},
    )
    with _app(channel, monkeypatch) as client:
        assert client.get("/liveness").status_code == 200


def test_credential_swap_disabled_channel_needs_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # credentials.enabled defaults False → no requirement, relay boots.
    channel = ChannelConfig(name="sabre", type=ChannelType.SABRE, host="sabre.test")
    with _app(channel, monkeypatch) as client:
        assert client.get("/liveness").status_code == 200


def _travelport(credentials: dict[str, object]) -> ChannelConfig:
    return ChannelConfig(
        name="travelport",
        type=ChannelType.TRAVELPORT,
        host="travelport.test",
        credentials=credentials,
    )


def test_swap_enabled_travelport_with_credentials_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _travelport({"enabled": True, "username": "assigned-user", "password": "assigned-pass"})

    with _app(channel, monkeypatch) as client:
        assert client.get("/liveness").status_code == 200


@pytest.mark.parametrize(
    "credentials",
    [
        {"enabled": True, "password": "assigned-pass"},
        {"enabled": True, "username": "assigned-user"},
        {"enabled": True, "username": "", "password": "assigned-pass"},
        {"enabled": True, "username": "assigned-user", "password": ""},
        {"enabled": True, "username": "bad:user", "password": "assigned-pass"},
        {"enabled": True, "username": "Universal API/assigned-user", "password": "assigned-pass"},
        {"enabled": True, "username": "assigned-user\n", "password": "assigned-pass"},
        {"enabled": True, "username": "assigned-user", "password": "assigned\u0007pass"},
        {"enabled": True, "username": "assigned-user", "password": "assigned\u0085pass"},
    ],
    ids=[
        "missing-username",
        "missing-password",
        "empty-username",
        "empty-password",
        "colon-username",
        "prefixed-username",
        "control-username",
        "control-password",
        "unicode-control-password",
    ],
)
def test_invalid_travelport_credentials_abort_without_values(
    monkeypatch: pytest.MonkeyPatch, credentials: dict[str, object]
) -> None:
    channel = _travelport(credentials)

    with pytest.raises(ValueError) as exc_info:  # noqa: PT012 - error raised on lifespan enter
        with _app(channel, monkeypatch) as client:
            client.get("/liveness")

    detail = str(exc_info.value)
    assert "travelport" in detail.lower()
    for secret in ("assigned-user", "assigned-pass", "bad:user", "assigned\u0007pass", "assigned\u0085pass"):
        assert secret not in detail


@pytest.mark.parametrize("legacy_key", ["soap_security", "soap_username", "soap_password"])
def test_obsolete_travelport_soap_credentials_abort(monkeypatch: pytest.MonkeyPatch, legacy_key: str) -> None:
    channel = _travelport(
        {
            "enabled": True,
            "username": "assigned-user",
            "password": "assigned-pass",
            legacy_key: "legacy-secret",
        }
    )

    with pytest.raises(ValueError) as exc_info:  # noqa: PT012 - error raised on lifespan enter
        with _app(channel, monkeypatch) as client:
            client.get("/liveness")

    assert legacy_key in str(exc_info.value)
    assert "legacy-secret" not in str(exc_info.value)


def test_disabled_travelport_swap_needs_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _travelport({"enabled": False, "soap_security": "ignored-secret"})

    with _app(channel, monkeypatch) as client:
        assert client.get("/liveness").status_code == 200
