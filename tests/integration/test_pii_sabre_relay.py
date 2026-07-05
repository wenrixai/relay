"""End-to-end Sabre PII baseline + credential swap over the relay (baked fallback rules).

No rules API is configured, so the relay loads the shipped ``rules_fallback.json`` Sabre
baseline. Responses get credential cleanup first (``BinarySecurityToken`` → ``ENC_`` token via
the Sabre handler) and PII redaction second; requests get de-anonymized then their SOAP
``Security`` header swapped for the configured fragment before reaching the channel.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.codec import decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.xml_ops import parse_bytes

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sabre"
KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'
SOAP_SECURITY = '<wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext">RELAY</wsse:Security>'


class MockSabre:
    """Serves a fixed Sabre fixture and records bodies the relay forwards upstream."""

    def __init__(self, response_fixture: str) -> None:
        self.body = (FIXTURES / response_fixture).read_bytes()
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.channel_bodies.append(request.read())
        return httpx.Response(200, content=self.body, headers={"content-type": "text/xml; charset=utf-8"})


def _client(mock: MockSabre, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    monkeypatch.delenv("RELAY_RULES_API_URL", raising=False)
    channel = ChannelConfig(
        name="sabre",
        type=ChannelType.SABRE,
        host="sabre.test",
        credentials={"soap_security": SOAP_SECURITY},
        pii=ChannelPII(enabled=True),
    )
    app = create_app(
        config=RelayConfig(channels=[channel]),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)),
    )
    return TestClient(app)


def _request_body() -> bytes:
    return (FIXTURES / "session_create_request.xml").read_bytes()


def test_price_quote_response_redacted_and_token_encrypted(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MockSabre("get_price_quote_response.xml")
    with _client(mock, monkeypatch) as client:
        response = client.post("/channel/sabre/op", content=_request_body(), headers={"content-type": "text/xml"})
    assert response.status_code == 200
    # Attribute-borne names are gone; reversible tokens are present.
    for gone in (b"TESTMSTR", b"MARY", b'lastName="TEST"'):
        assert gone not in response.content
    assert b"ENC_" in response.content
    # The Sabre session token was encrypted by the credential-cleanup stage (before redaction).
    assert b"SANITIZED!0!0" not in response.content
    root = parse_bytes(response.content)
    token = next(node.text for node in root.iter("*") if node.tag.endswith("BinarySecurityToken"))
    assert token is not None and token.startswith("ENC_")
    assert decrypt(token, Keyring.from_json(KEYRING_JSON)).endswith("SANITIZED!0!0")
    # Non-PII (agent locations) preserved.
    assert b"0HAH" in response.content


def test_request_security_header_swapped_not_leaked(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MockSabre("air_ticket_emd_response.xml")
    with _client(mock, monkeypatch) as client:
        response = client.post("/channel/sabre/op", content=_request_body(), headers={"content-type": "text/xml"})
    assert response.status_code == 200
    forwarded = mock.channel_bodies[-1]
    # Client-sent credentials are replaced by the configured fragment (UsernameToken with
    # unqualified Organization/Domain children never reaches the channel).
    assert b">RELAY<" in forwarded
    for gone in (b"1000001", b"FAKEPASS1", b"<Organization>", b"UsernameToken"):
        assert gone not in forwarded
    # Response PII (names) redacted for the client.
    assert b"JOHN" not in response.content and b"DOE" not in response.content
    assert b"ENC_" in response.content


def test_encrypted_token_round_trips_on_next_request(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MockSabre("air_ticket_emd_response.xml")
    with _client(mock, monkeypatch) as client:
        first = client.post("/channel/sabre/op", content=_request_body(), headers={"content-type": "text/xml"})
        root = parse_bytes(first.content)
        token = next(node.text for node in root.iter("*") if node.tag.endswith("BinarySecurityToken"))
        assert token is not None and token.startswith("ENC_")
        follow_up = (
            '<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/"'
            ' xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><soap-env:Header>'
            f"<wsse:Security><wsse:BinarySecurityToken>{token}</wsse:BinarySecurityToken></wsse:Security>"
            "</soap-env:Header><soap-env:Body><GetReservationRQ/></soap-env:Body></soap-env:Envelope>"
        )
        reply = client.post("/channel/sabre/op", content=follow_up.encode(), headers={"content-type": "text/xml"})
    assert reply.status_code == 200
    forwarded = mock.channel_bodies[-1]
    # De-anonymization restored the session token, then the security header swap replaced the
    # whole Security element with the configured fragment — no ENC_ token reaches the channel.
    assert b"ENC_" not in forwarded
    assert b">RELAY<" in forwarded
