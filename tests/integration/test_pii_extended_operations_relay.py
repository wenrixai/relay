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


def test_amadeus_third_party_remarks_redacted_end_to_end(
    relay_client_factory: RelayClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        relay_client_factory,
        monkeypatch,
        channel_type=ChannelType.AMADEUS,
        fixture="pnr_retrieve_third_party_remarks_response.xml",
    )
    with client:
        response = client.post("/channel/amadeus/op", content=b"<Ping/>", headers={"content-type": "text/xml"})
    assert response.status_code == 200
    # Orderer name, remark date of birth, person-linked identifiers, and the FP card.
    for value in (b"GREENE", b"ALICE", b"02FEB90", b"37000001", b"770000001", b"XXXXXXXXXX1111"):
        assert value not in response.content
    assert b"ENC_" in response.content
    # Organisation-level codes and the ticket number stay verbatim through the relay.
    assert b"CMP OPK000FI" in response.content
    assert b"PAX 105-2400000001/ETAY" in response.content


def test_sabre_third_party_remarks_redacted_end_to_end(
    relay_client_factory: RelayClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        relay_client_factory,
        monkeypatch,
        channel_type=ChannelType.SABRE,
        fixture="get_reservation_third_party_remarks_response.xml",
    )
    with client:
        response = client.post("/channel/sabre/op", content=b"<Ping/>", headers={"content-type": "text/xml"})
    assert response.status_code == 200
    # Third parties, identity documents in remarks, the history card fragment, and the
    # person-linked identifiers.
    for value in (
        b"DANA COHEN",
        b"MAYA",
        b"SAM BARNES",
        b"02FEB90",
        b"39000001",
        b"5XXXXXXXXXXX1111",
        b"12300001",
        b"712300001",
    ):
        assert value not in response.content
    assert b"ENC_" in response.content
    # Agency-agent identity and commercial data are operational and survive the relay.
    assert b"MARK TAYLOR" in response.content
    assert b"OIN TESTCORP" in response.content
    assert b"<stl19:RecordLocator>YPQGBZ</stl19:RecordLocator>" in response.content
