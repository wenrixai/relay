"""End-to-end Amadeus PII baseline over the relay, driven by the baked fallback rules.

No rules API is configured (``RELAY_RULES_API_URL`` unset), so the relay loads the shipped
``rules_fallback.json`` Amadeus baseline. A PNR_Reply response has its names/FF encrypted and
its contact/passport fields masked before reaching the client; encrypted tokens sent back on a
later request are de-anonymized to plaintext before the relay forwards them upstream.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pybase64
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.xml_ops import parse_bytes

FIXTURE = Path(__file__).parent.parent / "fixtures" / "amadeus" / "pnr_retrieve_response.xml"
KEYRING_JSON = json.dumps({"0": pybase64.b64encode(bytes([5]) * 32).decode()})


class MockChannel:
    """Serves the Amadeus PNR reply and records bodies the relay forwards upstream."""

    def __init__(self) -> None:
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.channel_bodies.append(request.read())
        return httpx.Response(
            200,
            content=FIXTURE.read_bytes(),
            headers={"content-type": "text/xml; charset=utf-8"},
        )


@pytest.fixture(name="mock_channel")
def mock_channel_fixture() -> MockChannel:
    return MockChannel()


@pytest.fixture(name="client")
def client_fixture(mock_channel: MockChannel, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    monkeypatch.delenv("RELAY_RULES_API_URL", raising=False)
    config = RelayConfig(
        channels=[
            ChannelConfig(
                name="amadeus",
                type=ChannelType.AMADEUS,
                host="channel.test",
                pii=ChannelPII(enabled=True),
            )
        ]
    )
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_channel.handler)),
    )
    return TestClient(app)


def _text(body: bytes, local_name: str) -> str:
    root = parse_bytes(body)
    return next(node.text or "" for node in root.xpath(f"//*[local-name()='{local_name}']"))


def test_response_redacted_for_client(client: TestClient) -> None:
    with client:
        response = client.post("/channel/amadeus/op", content=b"<Ping/>")
    assert response.status_code == 200
    # No plaintext PII survives; names became reversible tokens.
    for gone in (b"PARK", b"JANGBIN", b"00852-62374313", b"SEAFLY314", b"M037B6058", b"NH4144402077"):
        assert gone not in response.content
    assert b"ENC_" in response.content
    # Non-PII PNR reference is untouched.
    assert b"<controlNumber>DFMJER</controlNumber>" in response.content


def test_encrypted_name_round_trips_upstream(client: TestClient, mock_channel: MockChannel) -> None:
    with client:
        redacted = client.post("/channel/amadeus/op", content=b"<Ping/>").content
        surname_token = _text(redacted, "surname")
        assert surname_token.startswith("ENC_")
        request_xml = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            '<pnr:PNR_Add xmlns:pnr="http://xml.amadeus.com/PNRACC_17_1_1A"><pnr:traveller>'
            f"<pnr:surname>{surname_token}</pnr:surname>"
            "</pnr:traveller></pnr:PNR_Add></soap:Body></soap:Envelope>"
        )
        reply = client.post("/channel/amadeus/op", content=request_xml.encode(), headers={"content-type": "text/xml"})
    assert reply.status_code == 200
    forwarded = mock_channel.channel_bodies[-1]
    assert b"ENC_" not in forwarded
    assert b"<pnr:surname>PARK</pnr:surname>" in forwarded
