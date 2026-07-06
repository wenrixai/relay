"""Response Content-Encoding hygiene: httpx decodes the upstream body, so the relay must
never relay a stale `Content-Encoding` on the decoded bytes it forwards (fix #5)."""

from __future__ import annotations

import gzip

import httpx
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app

_XML = b"<Envelope><Body>hello</Body></Envelope>"


def _client(channel: ChannelConfig, handler: httpx.MockTransport) -> TestClient:
    return TestClient(
        create_app(config=RelayConfig(channels=[channel]), http_client=httpx.AsyncClient(transport=handler))
    )


def test_gzip_response_on_passthrough_channel_is_served_decodable() -> None:
    """No stage mutates the body (no creds, pii off): the decoded body must reach the client
    with no `Content-Encoding` header, so the client can read it."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=gzip.compress(_XML),
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)  # no creds, pii off
    with _client(channel, httpx.MockTransport(handler)) as client:
        response = client.post("/channel/tf/op", content=b"<Ping/>", headers={"content-type": "application/xml"})

    assert response.status_code == 200
    # Client sees the decoded body with no stale Content-Encoding descriptor.
    assert "content-encoding" not in {k.lower() for k in response.headers}
    assert response.content == _XML
