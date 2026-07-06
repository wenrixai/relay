"""Channel operation parsing and credential swap tests (Slice 3)."""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import etree

from channel_relay.channels import get_handler
from channel_relay.channels.base import CredentialSwapError, SwapContext
from channel_relay.channels.wsse import password_digest
from channel_relay.config.models import ChannelConfig, ChannelType
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.xml_ops import parse_bytes, serialize

FIXTURES = Path(__file__).parents[1] / "fixtures"
KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'


def _root(path: str) -> etree._Element:
    return parse_bytes((FIXTURES / path).read_bytes())


def _ctx(channel: ChannelConfig, headers: dict[str, str] | None = None) -> SwapContext:
    return SwapContext(channel=channel, headers={} if headers is None else headers, keyring=None)


def _enabled(credentials: dict[str, str] | None) -> dict[str, object]:
    return {"enabled": True, **credentials} if credentials is not None else {}


def _tf_channel(credentials: dict[str, str] | None = None) -> ChannelConfig:
    return ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, credentials=_enabled(credentials))


def _farelogix_channel(credentials: dict[str, str] | None = None) -> ChannelConfig:
    return ChannelConfig(name="flx", type=ChannelType.FARELOGIX_AA, credentials=_enabled(credentials))


def _ndc_channel(
    channel_type: ChannelType = ChannelType.BA_NDC_DIRECT,
    credentials: dict[str, str] | None = None,
) -> ChannelConfig:
    host = "la.test" if channel_type is ChannelType.LA_NDC_DIRECT else None
    return ChannelConfig(name=channel_type.value, type=channel_type, host=host, credentials=_enabled(credentials))


def _gds_channel(
    channel_type: ChannelType = ChannelType.AMADEUS,
    credentials: dict[str, str] | None = None,
) -> ChannelConfig:
    return ChannelConfig(name=channel_type.value, type=channel_type, host="gds.test", credentials=_enabled(credentials))


def _assert_swap_error(message: str, func: Callable[..., object], *args: object) -> None:
    with pytest.raises(CredentialSwapError, match=message):
        func(*args)


def test_registry_has_handler_for_every_channel_type() -> None:
    for channel_type in ChannelType:
        assert get_handler(channel_type).channel_type is channel_type


def test_travelfusion_operation_ignores_general_info_and_swaps_request() -> None:
    channel = _tf_channel(
        {
            "login_id": "relay-login",
            "xml_login_id": "relay-xml",
            "supplier_parameters": "market=US,currency=USD",
        }
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
    channel = _tf_channel({"login_id": "relay-login", "xml_login_id": "relay-xml"})
    root = _root("travelfusion/response.xml")

    assert get_handler(channel.type).swap_response(root, _ctx(channel)) is True

    xml = serialize(root).decode()
    assert "LoginId" not in xml
    assert "<Status>OK</Status>" in xml


def test_travelfusion_no_credentials_is_noop() -> None:
    channel = _tf_channel()
    root = _root("travelfusion/request.xml")
    response = _root("travelfusion/response.xml")
    handler = get_handler(channel.type)

    assert handler.requires_body_inspection(channel) is False
    assert handler.swap_request_body(root, _ctx(channel)) is False
    assert handler.swap_response(response, _ctx(channel)) is False


@pytest.mark.parametrize(
    ("message", "body", "credentials"),
    [
        ("operation element not found", b"<GeneralInfoItemList/>", {}),
        ("login elements not found", b"<Root><StartRouting/></Root>", {}),
        (
            "supplier parameter must be name=value",
            b"<Root><StartRouting><LoginId/><XmlLoginId/><CustomSupplierParameterList/></StartRouting></Root>",
            {"supplier_parameters": "bad"},
        ),
    ],
    ids=["missing-operation", "missing-login", "bad-supplier-parameter"],
)
def test_travelfusion_missing_operation_or_supplier_parameter_fails_closed(
    message: str, body: bytes, credentials: dict[str, str]
) -> None:
    handler = get_handler(ChannelType.TRAVELFUSION)
    channel = _tf_channel({"login_id": "login", "xml_login_id": "xml"} | credentials)

    _assert_swap_error(
        message,
        handler.swap_request_body,
        parse_bytes(body),
        _ctx(channel),
    )


def test_ndc_header_swaps_leave_body_unchanged() -> None:
    ba = _ndc_channel(ChannelType.BA_NDC_DIRECT, {"client_key": "ba-key"})
    la = _ndc_channel(ChannelType.LA_NDC_DIRECT, {"api_key": "la-key", "api_key_header": "X-LA-Key"})
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


def test_ndc_header_swap_no_credentials_is_noop_and_missing_key_fails_closed() -> None:
    handler = get_handler(ChannelType.BA_NDC_DIRECT)
    no_creds = _ndc_channel()
    missing_key = _ndc_channel(credentials={"api_key_header": "X-Key"})
    headers: dict[str, str] = {}

    handler.swap_request_headers(_ctx(no_creds, headers))
    assert headers == {}
    _assert_swap_error("missing credential client_key", handler.swap_request_headers, _ctx(missing_key, headers))


def test_farelogix_swaps_expected_attributes_and_subscription_header() -> None:
    channel = _farelogix_channel(
        {
            "subscription_key": "sub-key",
            "username": "relay-user",
            "password": "relay-pass",
            "agent": "relay-agent",
            "agent_user": "relay-agent-user",
            "agent_password": "relay-agent-pass",
            "agent_number": "relay-agency",
        }
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
    channel = _farelogix_channel(
        {
            "subscription_key": "sub-key",
            "username": "relay-user",
            "password": "relay-pass",
            "agent": "relay-agent",
            "agent_user": "relay-agent-user",
            "agent_password": "relay-agent-pass",
        }
    )
    root = parse_bytes(b"<Envelope><Body><AirShoppingRQ/></Body></Envelope>")

    _assert_swap_error("Farelogix", get_handler(channel.type).swap_request_body, root, _ctx(channel))


def test_farelogix_no_credentials_is_noop_and_missing_subscription_key_fails_closed() -> None:
    handler = get_handler(ChannelType.FARELOGIX_AA)
    no_creds = _farelogix_channel()
    missing_key = _farelogix_channel({"username": "u"})
    root = _root("farelogix/request.xml")

    assert handler.requires_body_inspection(no_creds) is False
    handler.swap_request_headers(_ctx(no_creds, {}))
    assert handler.swap_request_body(root, _ctx(no_creds)) is False
    _assert_swap_error("missing Farelogix subscription key", handler.swap_request_headers, _ctx(missing_key, {}))


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
        channel = _gds_channel(channel_type, {"soap_security": fragment})
        root = _root(fixture)
        handler = get_handler(channel_type)

        assert handler.parse_operation(root) == operation
        assert handler.swap_request_body(root, _ctx(channel)) is True

        xml = serialize(root).decode()
        assert "relay-token" in xml
        assert "caller" not in xml
        assert "caller-token" not in xml


def test_dynamic_username_token_built_when_soap_username_set() -> None:
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(
        ChannelType.AMADEUS,
        {"soap_username": "1000001", "soap_password": "S3cret!"},  # no static soap_security
    )
    root = _root("amadeus/request.xml")

    assert handler.swap_request_body(root, _ctx(channel)) is True
    swapped = parse_bytes(serialize(root))
    fields = {node.tag.split("}")[-1]: node for node in swapped.iter("*")}
    assert fields["Username"].text == "1000001"
    assert fields["Password"].get("Type").endswith("#PasswordDigest")
    # The digest recomputes from the emitted Nonce + Created.
    nonce = base64.b64decode(fields["Nonce"].text)
    created = fields["Created"].text
    assert fields["Password"].text == password_digest("S3cret!", nonce, created)
    # Client-sent credentials are gone.
    assert b"caller" not in serialize(root)


def test_dynamic_username_token_uses_fresh_nonce_each_request() -> None:
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(ChannelType.AMADEUS, {"soap_username": "u", "soap_password": "p"})

    def _nonce() -> str:
        root = _root("amadeus/request.xml")
        handler.swap_request_body(root, _ctx(channel))
        swapped = parse_bytes(serialize(root))
        return next(n.text or "" for n in swapped.iter("*") if n.tag.endswith("}Nonce"))

    assert _nonce() != _nonce()


def test_dynamic_username_token_rejects_bad_password_type() -> None:
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(
        ChannelType.AMADEUS,
        {"soap_username": "u", "soap_password": "p", "soap_password_type": "bogus"},
    )
    _assert_swap_error("soap_password_type", handler.swap_request_body, _root("amadeus/request.xml"), _ctx(channel))


def test_soap_security_xpath_target_variant_replaces_header() -> None:
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(
        credentials={
            "soap_security": "<Security><Token>relay</Token></Security>",
            "soap_security_target_xpath": "//*[local-name()='Security']",
        },
    )
    root = _root("amadeus/request.xml")

    assert handler.swap_request_body(root, _ctx(channel)) is True
    assert "relay" in serialize(root).decode()


@pytest.mark.parametrize(
    ("credentials", "message"),
    [
        ({"soap_security": "<Security/>", "soap_security_target_xpath": "//*["}, "invalid"),
        ({"soap_security": "<Security/>", "soap_security_target_xpath": "string(//*)"}, "not found"),
        ({"soap_security": "<Security/>", "soap_security_target_xpath": "//*[local-name()='Missing']"}, "not found"),
        ({"soap_security": "<Security><Token>"}, "parseable XML"),
    ],
    ids=["invalid-xpath", "scalar-xpath", "missing-target", "invalid-fragment"],
)
def test_soap_security_xpath_target_failures(credentials: dict[str, str], message: str) -> None:
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(credentials=credentials)

    _assert_swap_error(message, handler.swap_request_body, _root("amadeus/request.xml"), _ctx(channel))


@pytest.mark.parametrize(
    ("message", "body"),
    [
        ("SOAP Header not found", b"<Envelope/>"),
        ("SOAP Security header not found", b"<Envelope><Header/><Body/></Envelope>"),
    ],
    ids=["missing-header", "missing-security"],
)
def test_soap_security_missing_header_or_security_fails_closed(message: str, body: bytes) -> None:
    handler = get_handler(ChannelType.SABRE)
    channel = _gds_channel(ChannelType.SABRE, {"soap_security": "<Security/>"})

    assert handler.requires_body_inspection(_gds_channel(ChannelType.SABRE)) is False
    _assert_swap_error(message, handler.swap_request_body, parse_bytes(body), _ctx(channel))


def test_ndc_header_swap_replaces_client_sent_variant_case_insensitively() -> None:
    ba = _ndc_channel(credentials={"client_key": "ba-key"})
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
        channel = _gds_channel(channel_type, {"soap_security": "<Security/>"})
        root = _root(fixture)

        assert get_handler(channel_type).swap_response(root, SwapContext(channel=channel, headers={}, keyring=keyring))

        xml = serialize(root).decode()
        assert plaintext not in xml
        assert "ENC_" in xml


def test_soap_response_noop_and_missing_keyring_paths() -> None:
    keyring = Keyring.from_json(KEYRING_JSON)
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(credentials={"soap_security": "<Security/>"})
    no_creds_response = parse_bytes(b"<Envelope><SessionId>SESSION-123</SessionId></Envelope>")

    _assert_swap_error(
        "response auth encryption requires keyring",
        handler.swap_response,
        _root("amadeus/response_auth.xml"),
        _ctx(channel),
    )

    already_encrypted = parse_bytes(b"<Envelope><SessionId>ENC_aGVsbG8</SessionId></Envelope>")
    assert handler.swap_response(already_encrypted, SwapContext(channel, {}, keyring)) is False

    no_creds = ChannelConfig(name="gds-off", type=ChannelType.AMADEUS, credentials={"soap_security": "<Security/>"})
    assert handler.swap_response(no_creds_response, SwapContext(no_creds, {}, keyring)) is False
