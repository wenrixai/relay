"""End-to-end PII round-trip through the app: redact response → de-anonymize request (T2.6).

The mock channel is an httpx.MockTransport; the rules API is served by the same transport,
exercising the real startup fetch path. No real network anywhere.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import httpx
import pybase64
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.codec import TOKEN_RE
from channel_relay.pii.xml_ops import parse_bytes

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mock"
RULES_URL = "https://rules.wenrix.test/v1"
KEYRING_JSON = json.dumps({"0": pybase64.b64encode(bytes([9]) * 32).decode()})

REQUEST_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    '<soap:Body><req:PNR_Update xmlns:req="urn:mock:pnr">'
    "<req:Name>{name}</req:Name><req:Note note='{attr}'>x</req:Note>"
    "</req:PNR_Update></soap:Body></soap:Envelope>"
)


class MockChannel:
    """Serves the rules API and the mock channel; records forwarded request bodies."""

    def __init__(self) -> None:
        self.channel_bodies: list[bytes] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "rules.wenrix.test":
            return httpx.Response(200, text=(FIXTURES / "rules.json").read_text())
        self.channel_bodies.append(request.read())
        return httpx.Response(
            200,
            content=(FIXTURES / "soap_response.xml").read_bytes(),
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
                name="mock",
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


def extract_token(body: bytes, local_name: str) -> str:
    root = parse_bytes(body)
    value = root.xpath(f"//*[local-name()='{local_name}']")[0].text
    assert value is not None and TOKEN_RE.fullmatch(value)
    return value


def test_response_is_redacted(client: TestClient) -> None:
    with client:
        response = client.post("/channel/mock/op", content=b"<Ping/>", headers={"content-type": "text/xml"})
    assert response.status_code == 200
    assert b"John Smith" not in response.content
    assert b"john.smith@example.com" not in response.content
    token = extract_token(response.content, "Name")
    assert token.startswith("ENC_")


def test_round_trip_channel_receives_plaintext(client: TestClient, mock_channel: MockChannel) -> None:
    with client:
        redacted = client.post("/channel/mock/op", content=b"<Ping/>", headers={"content-type": "text/xml"}).content
        name_token = extract_token(redacted, "Name")
        root = parse_bytes(redacted)
        attr_token = root.xpath("//*[local-name()='Traveler']/@loyalty")[0]
        request_xml = REQUEST_TEMPLATE.format(name=name_token, attr=attr_token)
        reply = client.post(
            "/channel/mock/op",
            content=request_xml.encode(),
            headers={"content-type": "text/xml"},
        )
    assert reply.status_code == 200
    forwarded = mock_channel.channel_bodies[-1]
    assert b"John Smith" in forwarded
    assert b"FF-778899" in forwarded
    assert b"ENC_" not in forwarded


def test_gzip_request_round_trips(client: TestClient, mock_channel: MockChannel) -> None:
    with client:
        redacted = client.post("/channel/mock/op", content=b"<Ping/>", headers={"content-type": "text/xml"}).content
        name_token = extract_token(redacted, "Name")
        request_xml = REQUEST_TEMPLATE.format(name=name_token, attr="none")
        reply = client.post(
            "/channel/mock/op",
            content=gzip.compress(request_xml.encode()),
            headers={"content-type": "text/xml", "content-encoding": "gzip"},
        )
    assert reply.status_code == 200
    forwarded = mock_channel.channel_bodies[-1]
    assert b"John Smith" in gzip.decompress(forwarded)


def test_bad_token_returns_502_and_never_forwards(client: TestClient, mock_channel: MockChannel) -> None:
    bad = REQUEST_TEMPLATE.format(name="ENC_dG9vc2hvcnQ", attr="none")
    with client:
        response = client.post(
            "/channel/mock/op",
            content=bad.encode(),
            headers={"content-type": "text/xml"},
        )
    assert response.status_code == 502
    assert response.headers["x-wenrix-error"] == "pii_deanonymization_failed"
    payload = response.json()
    assert payload["reason"] == "pii_deanonymization_failed"
    assert mock_channel.channel_bodies == []  # request never reached the channel


def test_malformed_request_xml_returns_502(client: TestClient, mock_channel: MockChannel) -> None:
    with client:
        response = client.post(
            "/channel/mock/op",
            content=b"<broken><xml",
            headers={"content-type": "text/xml"},
        )
    assert response.status_code == 502
    assert response.headers["x-wenrix-error"] == "xml_parse_error"
    assert mock_channel.channel_bodies == []


def test_non_token_values_untouched(client: TestClient, mock_channel: MockChannel) -> None:
    request_xml = REQUEST_TEMPLATE.format(name="Plain Name ENC_not a token", attr="ENCODE_ME")
    with client:
        reply = client.post(
            "/channel/mock/op",
            content=request_xml.encode(),
            headers={"content-type": "text/xml"},
        )
    assert reply.status_code == 200
    forwarded = mock_channel.channel_bodies[-1]
    assert b"Plain Name ENC_not a token" in forwarded
    assert b"ENCODE_ME" in forwarded


def test_pii_disabled_channel_passes_through(mock_channel: MockChannel) -> None:
    config = RelayConfig(channels=[ChannelConfig(name="plain", type=ChannelType.TRAVELFUSION, host="channel.test")])
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_channel.handler)),
    )
    with TestClient(app) as test_client:
        response = test_client.post("/channel/plain/op", content=b"<Ping/>")
    assert response.status_code == 200
    assert b"John Smith" in response.content  # untouched: PII off for this channel


def test_force_redact_channel_needs_no_keyring(mock_channel: MockChannel, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RELAY_PII_KEYRING", raising=False)
    monkeypatch.setenv("RELAY_RULES_API_URL", RULES_URL)
    config = RelayConfig(
        channels=[
            ChannelConfig(
                name="mock",
                type=ChannelType.TRAVELFUSION,
                host="channel.test",
                pii=ChannelPII(enabled=True, force_redact=True),
            )
        ]
    )
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_channel.handler)),
    )
    with TestClient(app) as test_client:
        response = test_client.post("/channel/mock/op", content=b"<Ping/>", headers={"content-type": "text/xml"})
    assert response.status_code == 200
    assert b"John Smith" not in response.content
    assert b"john.smith@example.com" not in response.content
    assert b"ENC_" not in response.content
    name = parse_bytes(response.content).xpath("//*[local-name()='Name']")[0].text
    assert name == "REDACTED"


def test_logs_never_contain_pii_or_tokens(client: TestClient, mock_channel: MockChannel) -> None:
    import io

    from loguru import logger

    sink = io.StringIO()
    handle = logger.add(sink, level="DEBUG")
    try:
        with client:
            redacted = client.post("/channel/mock/op", content=b"<Ping/>", headers={"content-type": "text/xml"}).content
            name_token = extract_token(redacted, "Name")
            client.post(
                "/channel/mock/op",
                content=REQUEST_TEMPLATE.format(name=name_token, attr="none").encode(),
                headers={"content-type": "text/xml"},
            )
    finally:
        logger.remove(handle)
    output = sink.getvalue()
    assert "John Smith" not in output
    assert "john.smith@example.com" not in output
    assert "ENC_" not in output
    assert KEYRING_JSON not in output
