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
