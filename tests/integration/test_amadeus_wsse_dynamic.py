"""Amadeus dynamic WS-Security UsernameToken over the relay (fix #4).

A channel configured with `soap_username`/`soap_password` injects a fresh UsernameToken digest into
each forwarded request; the digest recomputes from the emitted Nonce + Created, and no client
credentials leak upstream.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.channels.wsse import password_digest
from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.xml_ops import parse_bytes

_PASSWORD = "S3cret!"
_REQUEST = (
    b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><soap:Header>'
    b"<wsse:Security><wsse:UsernameToken><wsse:Username>caller</wsse:Username>"
    b"<wsse:Password>caller-pass</wsse:Password></wsse:UsernameToken></wsse:Security>"
    b"</soap:Header><soap:Body><PNR_Retrieve/></soap:Body></soap:Envelope>"
)


class MockAmadeus:
    def __init__(self) -> None:
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.channel_bodies.append(request.read())
        return httpx.Response(200, content=b"<PNR_Reply/>", headers={"content-type": "text/xml"})


def _client(mock: MockAmadeus) -> TestClient:
    channel = ChannelConfig(
        name="amadeus",
        type=ChannelType.AMADEUS,
        host="amadeus.test",
        credentials={"soap_username": "1000001", "soap_password": _PASSWORD},
    )
    return TestClient(
        create_app(
            config=RelayConfig(channels=[channel]),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)),
        )
    )


def test_dynamic_username_token_reaches_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    # Credentialed Amadeus forces a keyring at startup even though PII is off.
    monkeypatch.setenv("RELAY_PII_KEYRING", '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}')
    mock = MockAmadeus()
    with _client(mock) as client:
        resp = client.post("/channel/amadeus/op", content=_REQUEST, headers={"content-type": "text/xml"})
    assert resp.status_code == 200

    forwarded = parse_bytes(mock.channel_bodies[-1])
    fields = {node.tag.split("}")[-1]: node for node in forwarded.iter("*")}
    assert fields["Username"].text == "1000001"
    nonce = base64.b64decode(fields["Nonce"].text)
    created = fields["Created"].text
    assert fields["Password"].text == password_digest(_PASSWORD, nonce, created)
    # Client-sent credentials never reach the channel.
    assert b"caller" not in mock.channel_bodies[-1]
    assert b"caller-pass" not in mock.channel_bodies[-1]
