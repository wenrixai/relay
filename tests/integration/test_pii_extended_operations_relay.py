"""Relay-level coverage for newly supported Amadeus and Sabre response operations."""

from __future__ import annotations

import json

import httpx
import pybase64
import pytest
from fastapi.testclient import TestClient
from tests.conftest import FIXTURES_DIR, RelayClientFactory

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType

KEYRING_JSON = json.dumps({"0": pybase64.b64encode(bytes([9]) * 32).decode()})


def _client(
    relay_client_factory: RelayClientFactory,
    monkeypatch: pytest.MonkeyPatch,
    *,
    channel_type: ChannelType,
    fixture: str,
) -> TestClient:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    body = (FIXTURES_DIR / channel_type.value / fixture).read_bytes()
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=body, headers={"content-type": "text/xml; charset=utf-8"})
    )
    channel = ChannelConfig(
        name=channel_type.value,
        type=channel_type,
        host="channel.test",
        pii=ChannelPII(enabled=True),
    )
    return relay_client_factory(channel, transport)


def test_amadeus_ticket_response_redacted_end_to_end(
    relay_client_factory: RelayClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        relay_client_factory,
        monkeypatch,
        channel_type=ChannelType.AMADEUS,
        fixture="ticket_process_extended_response.xml",
    )
    with client:
        response = client.post("/channel/amadeus/op", content=b"<Ping/>", headers={"content-type": "text/xml"})
    assert response.status_code == 200
    for value in (b"BROWN", b"ALICE", b"FF000001", b"411111XXXXXX1111", b"1229", b"ABC123"):
        assert value not in response.content
    assert b"ENC_" in response.content
    assert b"1720000000000" in response.content


def test_sabre_update_reservation_redacted_end_to_end(
    relay_client_factory: RelayClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        relay_client_factory,
        monkeypatch,
        channel_type=ChannelType.SABRE,
        fixture="update_reservation_pii_response.xml",
    )
    with client:
        response = client.post("/channel/sabre/op", content=b"<Ping/>", headers={"content-type": "text/xml"})
    assert response.status_code == 200
    for value in (b"BROWN", b"ALICE", b"TEST.USER@EXAMPLE.COM", b"15550000001", b"1990-02-02"):
        assert value not in response.content
    assert b"ENC_" in response.content
    assert b"PNR004" in response.content
