"""Forwarder integration tests for Slice 3 credential swap."""

from __future__ import annotations

import gzip

import httpx
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app

KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'


def _client(channel: ChannelConfig, handler: httpx.MockTransport) -> TestClient:
    app = create_app(config=RelayConfig(channels=[channel]), http_client=httpx.AsyncClient(transport=handler))
    app.state.settings.pii_keyring = KEYRING_JSON
    return TestClient(app)


def test_forwarder_applies_travelfusion_swap_before_upstream() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(
            200, content=b"<CommandList><Status>OK</Status></CommandList>", headers={"content-type": "text/xml"}
        )

    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "relay-login", "xml_login_id": "relay-xml"},
    )
    body = b"<CommandList><StartRouting><LoginId>caller</LoginId><XmlLoginId>caller</XmlLoginId></StartRouting></CommandList>"

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post("/channel/tf/CommandList", content=body, headers={"content-type": "text/xml"})

    assert resp.status_code == 200
    assert b"<LoginId>relay-login</LoginId>" in captured["req"].content
    assert b"caller" not in captured["req"].content


def test_forwarder_returns_credential_swap_failed_without_forwarding() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "relay-login", "xml_login_id": "relay-xml"},
    )

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/CommandList",
            content=b"<CommandList><StartRouting/></CommandList>",
            headers={"content-type": "text/xml"},
        )

    assert calls == 0
    assert resp.status_code == 502
    assert resp.json()["reason"] == "credential_swap_failed"
    assert resp.headers["x-wenrix-error"] == "credential_swap_failed"


def test_forwarder_sets_ndc_header_without_body_mutation() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(204)

    channel = ChannelConfig(
        name="ba", type=ChannelType.BA_NDC_DIRECT, credentials={"enabled": True, "client_key": "ba-key"}
    )
    body = b"<IATA_AirShoppingRQ><Payload>same</Payload></IATA_AirShoppingRQ>"

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post("/channel/ba/ndc", content=body, headers={"content-type": "application/xml"})

    assert resp.status_code == 204
    assert captured["req"].headers["Client-Key"] == "ba-key"
    assert captured["req"].content == body


def test_gzip_body_is_reencoded_when_credential_swap_requires_inspection() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "relay-login", "xml_login_id": "relay-xml"},
    )
    body = gzip.compress(
        b"<CommandList><StartRouting><LoginId>caller</LoginId><XmlLoginId>caller</XmlLoginId></StartRouting></CommandList>"
    )

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/CommandList",
            content=body,
            headers={"content-type": "text/xml", "content-encoding": "gzip"},
        )

    assert resp.status_code == 200
    assert captured["req"].headers["content-encoding"] == "gzip"
    assert b"relay-login" in gzip.decompress(captured["req"].content)


def test_request_deanonymization_runs_before_credential_swap() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "relay-login", "xml_login_id": "relay-xml"},
        pii=ChannelPII(enabled=True),
    )
    # Token is not on a credential field; it proves de-anonymization still happens before swap.
    from channel_relay.pii.codec import encrypt
    from channel_relay.pii.crypto import Keyring

    token = encrypt("Plain Passenger", Keyring.from_json(KEYRING_JSON))
    body = (
        f"<CommandList><StartRouting><LoginId>caller</LoginId><XmlLoginId>caller</XmlLoginId>"
        f"<Passenger>{token}</Passenger></StartRouting></CommandList>"
    ).encode()

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post("/channel/tf/CommandList", content=body, headers={"content-type": "text/xml"})

    assert resp.status_code == 200
    assert b"Plain Passenger" in captured["req"].content
    assert b"relay-login" in captured["req"].content


def test_ndc_oversize_body_is_forwarded_unchanged() -> None:
    # Header-only channels never inspect the body, so an oversize body must pass through, not 413.
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(204)

    channel = ChannelConfig(
        name="ba", type=ChannelType.BA_NDC_DIRECT, credentials={"enabled": True, "client_key": "ba-key"}
    )
    body = b"<IATA_AirShoppingRQ>" + b"<Filler>x</Filler>" * 200 + b"</IATA_AirShoppingRQ>"

    with _client(channel, httpx.MockTransport(handler)) as client:
        client.app.state.settings.max_inspect_bytes = 64
        resp = client.post("/channel/ba/ndc", content=body, headers={"content-type": "application/xml"})

    assert resp.status_code == 204
    assert captured["req"].headers["Client-Key"] == "ba-key"
    assert captured["req"].content == body


def test_ndc_malformed_body_is_forwarded_unchanged() -> None:
    # Header-only channels never parse the body, so malformed XML must pass through, not 502.
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(204)

    channel = ChannelConfig(
        name="ba", type=ChannelType.BA_NDC_DIRECT, credentials={"enabled": True, "client_key": "ba-key"}
    )
    body = b"<IATA_AirShoppingRQ><unclosed>"

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post("/channel/ba/ndc", content=body, headers={"content-type": "application/xml"})

    assert resp.status_code == 204
    assert captured["req"].headers["Client-Key"] == "ba-key"
    assert captured["req"].content == body


def test_gzip_body_deanonymized_and_swapped_in_single_round_trip() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "relay-login", "xml_login_id": "relay-xml"},
        pii=ChannelPII(enabled=True),
    )
    from channel_relay.pii.codec import encrypt
    from channel_relay.pii.crypto import Keyring

    token = encrypt("Plain Passenger", Keyring.from_json(KEYRING_JSON))
    plaintext = (
        f"<CommandList><StartRouting><LoginId>caller</LoginId><XmlLoginId>caller</XmlLoginId>"
        f"<Passenger>{token}</Passenger></StartRouting></CommandList>"
    ).encode()
    body = gzip.compress(plaintext)

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/CommandList",
            content=body,
            headers={"content-type": "text/xml", "content-encoding": "gzip"},
        )

    assert resp.status_code == 200
    assert captured["req"].headers["content-encoding"] == "gzip"
    decoded = gzip.decompress(captured["req"].content)
    assert b"Plain Passenger" in decoded  # PII de-anonymized
    assert b"relay-login" in decoded  # credential swapped
    assert token.encode() not in decoded


def test_sabre_response_auth_is_encrypted_before_returning_to_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
                b'xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><soap:Header><wsse:Security>'
                b"<wsse:BinarySecurityToken>SABRE-TOKEN</wsse:BinarySecurityToken>"
                b"</wsse:Security></soap:Header><soap:Body/></soap:Envelope>"
            ),
            headers={"content-type": "text/xml"},
        )

    channel = ChannelConfig(
        name="sabre",
        type=ChannelType.SABRE,
        host="sabre.test",
        credentials={"enabled": True, "soap_security": "<Security/>"},
    )
    request_body = (
        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Header>'
        b"<Security/></soap:Header><soap:Body><TravelItineraryReadRQ/></soap:Body></soap:Envelope>"
    )

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post("/channel/sabre", content=request_body, headers={"content-type": "text/xml"})

    assert resp.status_code == 200
    assert "SABRE-TOKEN" not in resp.text
    assert "ENC_" in resp.text
