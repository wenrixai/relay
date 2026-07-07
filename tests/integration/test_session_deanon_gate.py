"""Fix #3: for a credential-swap channel, encrypted session tokens must be de-anonymized on
the request path even when ``pii.enabled`` is False.

Amadeus is the discriminating case: its session fields live in the ``awsse:Session`` header,
*outside* the ``Security`` element that the credential swap replaces wholesale. So an ``ENC_``
session token replayed by the client survives the swap and would leak to the channel unless the
de-anonymization stage runs — which, before the fix, was gated on ``pii.enabled``.
"""

from __future__ import annotations

import json

import httpx
import pybase64
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.xml_ops import parse_bytes

KEYRING_JSON = json.dumps({"0": pybase64.b64encode(bytes([7]) * 32).decode()})
SOAP_SECURITY = '<wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext">RELAY</wsse:Security>'

# Response carries the Amadeus session in the awsse:Session header (outside Security).
_RESPONSE = (
    b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
    b' xmlns:awsse="http://xml.amadeus.com/2010/06/Session_v3"><soap:Header>'
    b"<awsse:Session><awsse:SessionId>SESSION-123</awsse:SessionId>"
    b"<awsse:SequenceNumber>42</awsse:SequenceNumber>"
    b"<awsse:SecurityToken>TOKEN-ABC</awsse:SecurityToken></awsse:Session>"
    b"</soap:Header><soap:Body><PNR_Reply/></soap:Body></soap:Envelope>"
)


class MockAmadeus:
    def __init__(self) -> None:
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.channel_bodies.append(request.read())
        return httpx.Response(200, content=_RESPONSE, headers={"content-type": "text/xml; charset=utf-8"})


def _client(mock: MockAmadeus, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    monkeypatch.delenv("RELAY_RULES_API_URL", raising=False)
    channel = ChannelConfig(
        name="amadeus",
        type=ChannelType.AMADEUS,
        host="amadeus.test",
        credentials={"enabled": True, "soap_security": SOAP_SECURITY},
        pii=ChannelPII(enabled=False),  # credential swap only; no PII
    )
    app = create_app(
        config=RelayConfig(channels=[channel]),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)),
    )
    return TestClient(app)


def _create_request() -> bytes:
    return (
        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
        b' xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><soap:Header>'
        b"<wsse:Security><wsse:UsernameToken><wsse:Username>caller</wsse:Username></wsse:UsernameToken>"
        b"</wsse:Security></soap:Header><soap:Body><Session_Create/></soap:Body></soap:Envelope>"
    )


def test_amadeus_session_tokens_deanonymized_with_pii_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MockAmadeus()
    with _client(mock, monkeypatch) as client:
        first = client.post("/channel/amadeus/op", content=_create_request(), headers={"content-type": "text/xml"})
        root = parse_bytes(first.content)
        session = {node.tag.split("}")[-1]: node.text for node in root.iter("*")}
        # Response auth encryption runs on the credential-swap feature, independent of pii.enabled.
        for field in ("SessionId", "SecurityToken"):
            assert session[field] is not None and session[field].startswith("ENC_")
        # SequenceNumber is a non-secret counter the client increments; it stays plaintext.
        assert session["SequenceNumber"] == "42"

        follow_up = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
            ' xmlns:awsse="http://xml.amadeus.com/2010/06/Session_v3"'
            ' xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><soap:Header>'
            "<wsse:Security><wsse:UsernameToken><wsse:Username>caller</wsse:Username></wsse:UsernameToken>"
            "</wsse:Security>"
            f"<awsse:Session><awsse:SessionId>{session['SessionId']}</awsse:SessionId>"
            f"<awsse:SequenceNumber>{session['SequenceNumber']}</awsse:SequenceNumber>"
            f"<awsse:SecurityToken>{session['SecurityToken']}</awsse:SecurityToken></awsse:Session>"
            "</soap:Header><soap:Body><PNR_Retrieve/></soap:Body></soap:Envelope>"
        )
        reply = client.post("/channel/amadeus/op", content=follow_up.encode(), headers={"content-type": "text/xml"})

    assert reply.status_code == 200
    forwarded = mock.channel_bodies[-1]
    # The replayed session tokens must be decrypted before reaching the channel.
    assert b"ENC_" not in forwarded
    assert b"<awsse:SessionId>SESSION-123</awsse:SessionId>" in forwarded
    assert b"<awsse:SecurityToken>TOKEN-ABC</awsse:SecurityToken>" in forwarded
