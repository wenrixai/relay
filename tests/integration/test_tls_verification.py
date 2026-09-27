"""Mandatory upstream TLS verification.

One process, one upstream pool, always verifying: there is no per-channel client selection and no
configuration — channel field or `RELAY_*` setting — that can weaken transport security.
"""

from __future__ import annotations

import httpx
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


def test_shared_client_verifies_tls_for_every_channel() -> None:
    app = create_app(config=_config())
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200
        for url in ("https://tf.test", "https://staging.test"):
            assert _ssl_verify_mode(app.state.client, url) != "CERT_NONE"
