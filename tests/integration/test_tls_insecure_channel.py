"""Per-channel TLS verification opt-out (`tls.insecure_skip_verify`).

Verifies the second, insecure-TLS httpx client is built only when needed, and that
forwarding for an insecure-TLS channel uses it while every other channel keeps using the
verifying client.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app


def test_no_insecure_client_when_no_channel_opts_out(monkeypatch: pytest.MonkeyPatch) -> None:
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, host="tf.test")])
    app = create_app(
        config=config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200
        assert app.state.insecure_client is None


def test_insecure_client_built_when_a_channel_opts_out(monkeypatch: pytest.MonkeyPatch) -> None:
    config = RelayConfig(
        channels=[
            ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, host="tf.test"),
            ChannelConfig(
                name="staging",
                type=ChannelType.TRAVELPORT,
                host="staging.test",
                tls={"insecure_skip_verify": True},
            ),
        ]
    )
    app = create_app(
        config=config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200
        assert app.state.insecure_client is not None
        assert app.state.insecure_client is not app.state.client


def test_insecure_tls_channel_forwards_via_insecure_client(monkeypatch: pytest.MonkeyPatch) -> None:
    verifying_calls: list[str] = []
    insecure_calls: list[str] = []

    def verifying_handle(request: httpx.Request) -> httpx.Response:
        verifying_calls.append(str(request.url))
        return httpx.Response(200, content=b"<ok/>")

    def insecure_handle(request: httpx.Request) -> httpx.Response:
        insecure_calls.append(str(request.url))
        return httpx.Response(200, content=b"<ok/>")

    config = RelayConfig(
        channels=[
            ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, host="tf.test"),
            ChannelConfig(
                name="staging",
                type=ChannelType.TRAVELPORT,
                host="staging.test",
                tls={"insecure_skip_verify": True},
            ),
        ]
    )
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(verifying_handle)),
        insecure_http_client=httpx.AsyncClient(transport=httpx.MockTransport(insecure_handle)),
    )
    with TestClient(app) as client:
        assert client.get("/channel/tf/search").status_code == 200
        assert client.get("/channel/staging/search").status_code == 200

    # The verifying client also serves the startup rules fetch, so assert by URL content
    # rather than call count.
    assert any("tf.test" in url for url in verifying_calls)
    assert not any("staging.test" in url for url in verifying_calls)
    assert insecure_calls == [url for url in insecure_calls if "staging.test" in url]
    assert insecure_calls
