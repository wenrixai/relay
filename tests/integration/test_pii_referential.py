"""End-to-end referential redaction: names extracted from structured fields are scrubbed from
free-text remark fields (Amadeus/Sabre style), and embedded tokens round-trip back to plaintext.

The mock channel serves both the rules API and the channel over one httpx.MockTransport; no real
network. Mirrors ``test_pii_roundtrip`` for a channel that carries PII inside remark prose.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.xml_ops import parse_bytes

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mock"
RULES_URL = "https://rules.wenrix.test/v1"
KEYRING_JSON = json.dumps({"0": base64.b64encode(bytes([5]) * 32).decode()})


class MockChannel:
    """Serves the rules API and the Amadeus-style channel; records forwarded request bodies."""

    def __init__(self) -> None:
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "rules.wenrix.test":
            return httpx.Response(200, text=(FIXTURES / "remark_rules.json").read_text())
        self.channel_bodies.append(request.read())
        return httpx.Response(
            200,
            content=(FIXTURES / "amadeus_remark_response.xml").read_bytes(),
            headers={"content-type": "text/xml; charset=utf-8"},
        )


@pytest.fixture(name="mock_channel")
def mock_channel_fixture() -> MockChannel:
    return MockChannel()


@pytest.fixture(name="client")
def client_fixture(mock_channel: MockChannel, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    monkeypatch.setenv("RELAY_RULES_API_URL", RULES_URL)
    config = RelayConfig(
        channels=[
            ChannelConfig(
                name="amd",
                type=ChannelType.TRAVELFUSION,
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


def _remark_texts(body: bytes) -> list[str]:
    root = parse_bytes(body)
    return [node.text or "" for node in root.xpath("//*[local-name()='remarkText']")]


def test_name_scrubbed_from_remark_response(client: TestClient) -> None:
    with client:
        response = client.post("/channel/amd/op", content=b"<Ping/>")
    assert response.status_code == 200
    # No plaintext name survives, in structured fields OR remark prose.
    assert b"JOHN" not in response.content
    assert b"SMITH" not in response.content
    remarks = _remark_texts(response.content)
    assert remarks[0].startswith("RM PSGR ") and "WHEELCHAIR ASSISTANCE AT GATE" in remarks[0]
    assert "ENC_" in remarks[0]


def test_remark_token_round_trips_to_channel(client: TestClient, mock_channel: MockChannel) -> None:
    with client:
        redacted = client.post("/channel/amd/op", content=b"<Ping/>").content
        redacted_remark = _remark_texts(redacted)[0]
        # Send the redacted remark (embedded ENC_ tokens) back to the channel.
        request_xml = (
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            '<pnr:PNR_Add xmlns:pnr="urn:amadeus:pnr"><pnr:remarkText>'
            f"{redacted_remark}"
            "</pnr:remarkText></pnr:PNR_Add></soap:Body></soap:Envelope>"
        )
        reply = client.post("/channel/amd/op", content=request_xml.encode(), headers={"content-type": "text/xml"})
    assert reply.status_code == 200
    forwarded = mock_channel.channel_bodies[-1]
    assert b"ENC_" not in forwarded
    assert b"RM PSGR JOHN SMITH RQ WHEELCHAIR ASSISTANCE AT GATE" in forwarded
