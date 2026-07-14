"""Forwarder integration tests for Slice 3 credential swap."""

from __future__ import annotations

import base64
import gzip
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.xml_ops import parse_bytes

KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'
FIXTURES = Path(__file__).parents[1] / "fixtures"


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


def test_header_only_ndc_json_passes_through_without_inspection() -> None:
    captured: dict[str, httpx.Request] = {}
    response_body = b'{"offer":"unchanged"}'

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, content=response_body, headers={"content-type": "application/json"})

    channel = ChannelConfig(
        name="ba", type=ChannelType.BA_NDC_DIRECT, credentials={"enabled": True, "client_key": "ba-key"}
    )
    request_body = b'{"shopping":"unchanged"}'

    with _client(channel, httpx.MockTransport(handler)) as client:
        resp = client.post("/channel/ba/ndc", content=request_body, headers={"content-type": "application/json"})

    assert resp.status_code == 200
    assert resp.content == response_body
    assert captured["req"].headers["Client-Key"] == "ba-key"
    assert captured["req"].content == request_body


def _travelport_channel() -> ChannelConfig:
    return ChannelConfig(
        name="travelport",
        type=ChannelType.TRAVELPORT,
        host="travelport.test",
        credentials={"enabled": True, "username": "assigned-user", "password": "assigned-pass"},
        pii=ChannelPII(enabled=False),
    )


def test_travelport_basic_auth_replaces_caller_without_body_credentials() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(
            200,
            content=b"<PingRsp>connectivity-check</PingRsp>",
            headers={"content-type": "text/xml"},
        )

    body = (FIXTURES / "travelport/request.xml").read_bytes()
    with _client(_travelport_channel(), httpx.MockTransport(handler)) as client:
        response = client.post(
            "/channel/travelport/SystemService",
            content=body,
            headers={"content-type": "text/xml", "authorization": "Basic Y2FsbGVyOnNlY3JldA=="},
        )

    assert response.status_code == 200
    expected = base64.b64encode(b"Universal API/assigned-user:assigned-pass").decode("ascii")
    authorization = [value for name, value in captured["req"].headers.multi_items() if name == "authorization"]
    assert authorization == [f"Basic {expected}"]
    assert "Y2FsbGVyOnNlY3JldA==" not in authorization[0]
    forwarded = captured["req"].content
    assert b"UsernameToken" not in forwarded
    root = parse_bytes(forwarded)
    fields = {element.tag.split("}")[-1]: element for element in root.iter("*")}
    assert fields["PingReq"].text == "connectivity-check"
    assert fields["PingReq"].get("TargetBranch") == "TESTBRANCH"


class _TravelportSessionMock:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self.requests) == 1:
            content = (FIXTURES / "travelport/booking_start_response.xml").read_bytes()
        else:
            content = b"<BookingTravelerRsp/>"
        return httpx.Response(200, content=content, headers={"content-type": "text/xml"})


def _session_key(response: httpx.Response) -> str:
    root = parse_bytes(response.content)
    return next(
        value
        for element in root.iter("*")
        for name, value in element.attrib.items()
        if name.split("}")[-1] == "SessionKey"
    )


def _session_request(token: str) -> bytes:
    return (
        (FIXTURES / "travelport/session_follow_up_request.xml")
        .read_bytes()
        .replace(b"TEST-SESSION-0001", token.encode())
    )


def test_travelport_session_key_is_encrypted_and_replayed_with_pii_disabled() -> None:
    mock = _TravelportSessionMock()
    with _client(_travelport_channel(), httpx.MockTransport(mock.handler)) as client:
        first = client.post(
            "/channel/travelport/SharedBookingService",
            content=(FIXTURES / "travelport/request.xml").read_bytes(),
            headers={"content-type": "text/xml"},
        )
        token = _session_key(first)
        second = client.post(
            "/channel/travelport/SharedBookingService",
            content=_session_request(token),
            headers={"content-type": "text/xml"},
        )

    assert first.status_code == 200
    assert token.startswith("ENC_")
    assert b"TEST-SESSION-0001" not in first.content
    assert second.status_code == 200
    forwarded = mock.requests[-1].content
    assert b"ENC_" not in forwarded
    root = parse_bytes(forwarded)
    values = [
        value
        for element in root.iter("*")
        for name, value in element.attrib.items()
        if name.split("}")[-1] in {"id", "SessionKey"}
    ]
    assert values == ["TEST-SESSION-0001", "TEST-SESSION-0001"]


def test_travelport_gzip_session_replay_restores_both_token_locations() -> None:
    mock = _TravelportSessionMock()
    with _client(_travelport_channel(), httpx.MockTransport(mock.handler)) as client:
        first = client.post(
            "/channel/travelport/SharedBookingService",
            content=(FIXTURES / "travelport/request.xml").read_bytes(),
            headers={"content-type": "text/xml"},
        )
        token = _session_key(first)
        second = client.post(
            "/channel/travelport/SharedBookingService",
            content=gzip.compress(_session_request(token)),
            headers={"content-type": "text/xml", "content-encoding": "gzip"},
        )

    assert second.status_code == 200
    request = mock.requests[-1]
    assert request.headers["content-encoding"] == "gzip"
    forwarded = gzip.decompress(request.content)
    assert forwarded.count(b"TEST-SESSION-0001") == 2
    assert b"ENC_" not in forwarded


def test_travelport_response_session_cleanup_fails_closed_without_keyring() -> None:
    mock = _TravelportSessionMock()
    with _client(_travelport_channel(), httpx.MockTransport(mock.handler)) as client:
        client.app.state.keyring = None
        response = client.post(
            "/channel/travelport/SharedBookingService",
            content=(FIXTURES / "travelport/request.xml").read_bytes(),
            headers={"content-type": "text/xml"},
        )

    assert response.status_code == 502
    assert response.json()["reason"] == "credential_swap_failed"
    assert b"TEST-SESSION-0001" not in response.content


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
