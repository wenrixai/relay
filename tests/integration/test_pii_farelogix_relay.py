"""End-to-end Farelogix PII baseline over the relay (baked fallback rules).

A ``farelogix-aa`` channel exercises the family alias: the rules are keyed on the ``farelogix``
family, while the channel type is the per-airline ``farelogix-aa``. The relay must still redact
the response, proving ``ChannelType.family`` is wired into the redaction alias tuple.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pybase64
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures" / "farelogix"
KEYRING_JSON = pybase64.b64encode(bytes([7]) * 32).decode()


class MockFarelogix:
    """Serves a fixed Farelogix response and records forwarded request bodies."""

    def __init__(self, response_fixture: str) -> None:
        self.body = (FIXTURES / response_fixture).read_bytes()
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.channel_bodies.append(request.read())
        return httpx.Response(200, content=self.body, headers={"content-type": "text/xml; charset=utf-8"})


def _client(mock: MockFarelogix, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    channel = ChannelConfig(
        name="farelogix-aa",
        type=ChannelType.FARELOGIX_AA,
        host="aa.farelogix.test",
        pii=ChannelPII(enabled=True),
    )
    app = create_app(
        config=RelayConfig(channels=[channel]),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)),
    )
    return TestClient(app)


def test_farelogix_variant_response_redacted_via_family_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MockFarelogix("order_view_response.xml")
    with _client(mock, monkeypatch) as client:
        response = client.post("/channel/farelogix-aa", content=b"<ping/>", headers={"content-type": "text/xml"})

    assert response.status_code == 200
    body = response.content
    # Structured PII is scrubbed even though the channel type is farelogix-aa, not farelogix.
    for gone in (
        b"DAVE.DOE@EXAMPLE.COM",
        b"17865554433",
        b"X1234321",
        b"<Surname>DOE</Surname>",
        b"01MAR77",
        b"<NameTitle>MR</NameTitle>",
        b"<IssuingCountryCode>ROU</IssuingCountryCode>",
        b"2023-12-06",
        b"2033-12-04",
    ):
        assert gone not in body
    # Operational identifiers survive.
    assert b"BMSHY5" in body and b"00157549767336" in body
