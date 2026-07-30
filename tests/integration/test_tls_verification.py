"""Relay-wide upstream TLS verification (`RELAY_UPSTREAM_TLS_VERIFY`).

One process, one upstream pool, one TLS policy: there is no per-channel client selection and
no channel-level way to weaken transport security.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app


def _config() -> RelayConfig:
    return RelayConfig(
        channels=[
            ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, host="tf.test"),
            ChannelConfig(name="staging", type=ChannelType.TRAVELPORT, host="staging.test"),
        ]
    )


def _ssl_verify_mode(app_client: httpx.AsyncClient, url: str) -> str:
    """The client's effective TLS verify mode — httpx exposes it only via privates."""
    transport = app_client._transport_for_url(httpx.URL(url))
    return str(transport._pool._ssl_context.verify_mode.name)


def test_app_state_has_no_second_client() -> None:
    app = create_app(
        config=_config(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200
        assert not hasattr(app.state, "insecure_client")


def test_create_app_rejects_insecure_client_injection() -> None:
    # The dual-pool test hook is gone; a stale caller must fail loudly, not be silently ignored.
    with pytest.raises(TypeError):
        create_app(insecure_http_client=httpx.AsyncClient())  # type: ignore[call-arg]


def test_every_channel_forwards_via_the_shared_client() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"<ok/>")

    app = create_app(config=_config(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    with TestClient(app) as client:
        assert client.get("/channel/tf/search").status_code == 200
        assert client.get("/channel/staging/search").status_code == 200

    assert any("tf.test" in url for url in calls)
    assert any("staging.test" in url for url in calls)


def test_shared_client_verifies_tls_by_default() -> None:
    app = create_app(config=_config())
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200
        assert _ssl_verify_mode(app.state.client, "https://staging.test") != "CERT_NONE"


def test_relay_wide_toggle_disables_verification_for_every_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELAY_UPSTREAM_TLS_VERIFY", "false")
    app = create_app(config=_config())
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200
        for url in ("https://tf.test", "https://staging.test"):
            assert _ssl_verify_mode(app.state.client, url) == "CERT_NONE"
