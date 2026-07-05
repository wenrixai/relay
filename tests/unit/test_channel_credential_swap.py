"""Channel operation parsing and credential swap tests (Slice 3)."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from channel_relay.channels import get_handler
from channel_relay.channels.base import CredentialSwapError, SwapContext
from channel_relay.config.models import ChannelConfig, ChannelType
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.xml_ops import parse_bytes, serialize

FIXTURES = Path(__file__).parents[1] / "fixtures"
KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'


def _root(path: str) -> etree._Element:
    return parse_bytes((FIXTURES / path).read_bytes())


def _ctx(channel: ChannelConfig, headers: dict[str, str] | None = None) -> SwapContext:
    return SwapContext(channel=channel, headers={} if headers is None else headers, keyring=None)


def test_registry_has_handler_for_every_channel_type() -> None:
    for channel_type in ChannelType:
        assert get_handler(channel_type).channel_type is channel_type


def test_travelfusion_operation_ignores_general_info_and_swaps_request() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={
            "login_id": "relay-login",
            "xml_login_id": "relay-xml",
            "supplier_parameters": "market=US,currency=USD",
        },
    )
    root = _root("travelfusion/request.xml")
    handler = get_handler(channel.type)

    assert handler.parse_operation(root) == "StartRouting"
    assert handler.swap_request_body(root, _ctx(channel)) is True

    xml = serialize(root).decode()
    assert "<LoginId>relay-login</LoginId>" in xml
    assert "<XmlLoginId>relay-xml</XmlLoginId>" in xml
    assert "<Name>market</Name>" in xml
    assert "<Value>US</Value>" in xml
    assert "old-value" not in xml


def test_travelfusion_response_strips_login_fields() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"login_id": "relay-login", "xml_login_id": "relay-xml"},
    )
    root = _root("travelfusion/response.xml")

    assert get_handler(channel.type).swap_response(root, _ctx(channel)) is True

    xml = serialize(root).decode()
    assert "LoginId" not in xml
    assert "<Status>OK</Status>" in xml


def test_ndc_header_swaps_leave_body_unchanged() -> None:
    ba = ChannelConfig(name="ba", type=ChannelType.BA_NDC_DIRECT, credentials={"client_key": "ba-key"})
    la = ChannelConfig(
        name="la",
        type=ChannelType.LA_NDC_DIRECT,
        host="la.test",
        credentials={"api_key": "la-key", "api_key_header": "X-LA-Key"},
    )
    ba_root = _root("ba/request.xml")
    la_root = _root("la/request.xml")
    ba_headers: dict[str, str] = {}
    la_headers: dict[str, str] = {}

    assert get_handler(ba.type).parse_operation(ba_root) == "IATA_AirShoppingRQ"
    assert get_handler(ba.type).swap_request_headers(_ctx(ba, ba_headers)) is None
    assert get_handler(ba.type).swap_request_body(ba_root, _ctx(ba, ba_headers)) is False
    assert ba_headers == {"Client-Key": "ba-key"}
    assert serialize(ba_root) == serialize(_root("ba/request.xml"))

    assert get_handler(la.type).parse_operation(la_root) == "IATA_OrderCreateRQ"
    assert get_handler(la.type).swap_request_headers(_ctx(la, la_headers)) is None
    assert get_handler(la.type).swap_request_body(la_root, _ctx(la, la_headers)) is False
    assert la_headers == {"X-LA-Key": "la-key"}
    assert serialize(la_root) == serialize(_root("la/request.xml"))


def test_farelogix_swaps_expected_attributes_and_subscription_header() -> None:
    channel = ChannelConfig(
        name="flx",
        type=ChannelType.FARELOGIX_AA,
        credentials={
            "subscription_key": "sub-key",
            "username": "relay-user",
            "password": "relay-pass",
            "agent": "relay-agent",
            "agent_user": "relay-agent-user",
            "agent_password": "relay-agent-pass",
            "agent_number": "relay-agency",
        },
    )
    root = _root("farelogix/request.xml")
    headers: dict[str, str] = {}

    assert get_handler(channel.type).parse_operation(root) == "AirShoppingRQ"
    assert get_handler(channel.type).swap_request_headers(_ctx(channel, headers)) is None
    assert get_handler(channel.type).swap_request_body(root, _ctx(channel, headers)) is True

    xml = serialize(root).decode()
    assert headers == {"Ocp-Apim-Subscription-Key": "sub-key"}
    assert 'u="relay-user"' in xml
    assert 'p="relay-pass"' in xml
    assert 'agt="relay-agent"' in xml
    assert 'agtpwd="relay-agent-pass"' in xml
    assert 'agy="relay-agency"' in xml
    assert 'user="relay-agent-user"' in xml
    assert "caller-user" not in xml


def test_farelogix_missing_required_elements_fails_closed() -> None:
    channel = ChannelConfig(
        name="flx",
        type=ChannelType.FARELOGIX_AA,
        credentials={
            "subscription_key": "sub-key",
            "username": "relay-user",
            "password": "relay-pass",
            "agent": "relay-agent",
            "agent_user": "relay-agent-user",
            "agent_password": "relay-agent-pass",
        },
    )
    root = parse_bytes(b"<Envelope><Body><AirShoppingRQ/></Body></Envelope>")

    try:
        get_handler(channel.type).swap_request_body(root, _ctx(channel))
    except CredentialSwapError:
        pass
    else:  # pragma: no cover - assertion path
        raise AssertionError("expected CredentialSwapError")


def test_soap_security_fragment_replaces_header_for_gds_channels() -> None:
    fragment = (
        '<wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext">'
        "<wsse:BinarySecurityToken>relay-token</wsse:BinarySecurityToken>"
        "</wsse:Security>"
    )
    for channel_type, fixture, operation in [
        (ChannelType.AMADEUS, "amadeus/request.xml", "PNR_Retrieve"),
        (ChannelType.SABRE, "sabre/request.xml", "TravelItineraryReadRQ"),
        (ChannelType.TRAVELPORT, "travelport/request.xml", "UniversalRecordRetrieveReq"),
    ]:
        channel = ChannelConfig(
            name=channel_type.value, type=channel_type, host="gds.test", credentials={"soap_security": fragment}
        )
        root = _root(fixture)
        handler = get_handler(channel_type)

        assert handler.parse_operation(root) == operation
        assert handler.swap_request_body(root, _ctx(channel)) is True

        xml = serialize(root).decode()
        assert "relay-token" in xml
        assert "caller" not in xml
        assert "caller-token" not in xml


def test_ndc_header_swap_replaces_client_sent_variant_case_insensitively() -> None:
    ba = ChannelConfig(name="ba", type=ChannelType.BA_NDC_DIRECT, credentials={"client_key": "ba-key"})
    # A client-supplied lowercase variant must not survive alongside the relay-injected header.
    headers = {"client-key": "caller-key", "accept": "application/xml"}

    get_handler(ba.type).swap_request_headers(_ctx(ba, headers))

    assert [key for key in headers if key.lower() == "client-key"] == ["Client-Key"]
    assert headers["Client-Key"] == "ba-key"
    assert headers["accept"] == "application/xml"


def test_amadeus_and_sabre_response_auth_fields_are_encrypted() -> None:
    keyring = Keyring.from_json(KEYRING_JSON)
    for channel_type, fixture, plaintext in [
        (ChannelType.AMADEUS, "amadeus/response_auth.xml", "SESSION-123"),
        (ChannelType.SABRE, "sabre/response_auth.xml", "SABRE-TOKEN"),
    ]:
        channel = ChannelConfig(
            name=channel_type.value, type=channel_type, host="gds.test", credentials={"soap_security": "<Security/>"}
        )
        root = _root(fixture)

        assert get_handler(channel_type).swap_response(root, SwapContext(channel=channel, headers={}, keyring=keyring))

        xml = serialize(root).decode()
        assert plaintext not in xml
        assert "ENC_" in xml
