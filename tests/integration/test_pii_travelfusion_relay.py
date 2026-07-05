"""End-to-end Travelfusion PII baseline + credential swap over the relay."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.codec import decrypt
from channel_relay.pii.crypto import Keyring

FIXTURES = Path(__file__).parent.parent / "fixtures" / "travelfusion"
KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'


class MockTravelfusion:
    """Serves a fixed Travelfusion fixture and records bodies forwarded upstream."""

    def __init__(self, response_fixture: str) -> None:
        self.body = (FIXTURES / response_fixture).read_bytes()
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.channel_bodies.append(request.read())
        return httpx.Response(200, content=self.body, headers={"content-type": "text/xml; charset=utf-8"})


def _client(mock: MockTravelfusion, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    monkeypatch.delenv("RELAY_RULES_API_URL", raising=False)
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"login_id": "relay-login", "xml_login_id": "relay-xml"},
        pii=ChannelPII(enabled=True),
    )
    app = create_app(
        config=RelayConfig(channels=[channel]),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)),
    )
    return TestClient(app)


def test_travelfusion_route_name_uses_type_rules_and_swaps_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MockTravelfusion("get_booking_details_payment_response.xml")

    with _client(mock, monkeypatch) as client:
        response = client.post(
            "/channel/tf/CommandList",
            content=(FIXTURES / "request.xml").read_bytes(),
            headers={"content-type": "text/xml"},
        )

    assert response.status_code == 200
    forwarded = mock.channel_bodies[-1]
    assert b"<LoginId>relay-login</LoginId>" in forwarded
    assert b"<XmlLoginId>relay-xml</XmlLoginId>" in forwarded
    assert b"caller-login" not in forwarded and b"caller-xml" not in forwarded

    for gone in (b"4111111111111111", b"billing@example.test", b"<LoginId>", b"<XmlLoginId>"):
        assert gone not in response.content
    assert b"ENC_" in response.content
    assert b"MasterCard" in response.content

    token = response.text.split("<Email>", maxsplit=1)[1].split("</Email>", maxsplit=1)[0]
    assert decrypt(token, Keyring.from_json(KEYRING_JSON)) == "billing@example.test"
