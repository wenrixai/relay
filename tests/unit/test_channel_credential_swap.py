"""Channel operation parsing and credential swap tests (Slice 3).

Every credential literal below (`relay-pass`, `assigned-pass`, `la-key`, ...) is a synthetic
marker string whose only purpose is to assert that the swap stage rewrote the right SOAP node or
header. None is a real or reusable secret; real credentials come from `relay.json` at runtime.
Snyk Code flags these as CWE-798 "hardcoded password" — see the `exclude: code:` block in `.snyk`.
"""

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


def _travelport_channel(credentials: dict[str, str] | None = None) -> ChannelConfig:
    return ChannelConfig(
        name="travelport",
        type=ChannelType.TRAVELPORT,
        host="travelport.test",
        credentials=_enabled(credentials),
    )


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


_SOAP_FRAGMENT = (
    '<wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext">'
    "<wsse:BinarySecurityToken>relay-token</wsse:BinarySecurityToken>"
    "</wsse:Security>"
)


def test_soap_security_fragment_replaces_amadeus_username_token() -> None:
    channel = _gds_channel(ChannelType.AMADEUS, {"soap_security": _SOAP_FRAGMENT})
    root = _root("amadeus/request.xml")
    handler = get_handler(ChannelType.AMADEUS)

    assert handler.parse_operation(root) == "PNR_Retrieve"
    assert handler.swap_request_body(root, _ctx(channel)) is True

    xml = serialize(root).decode()
    assert "relay-token" in xml
    assert "caller" not in xml


def test_travelport_sets_exact_basic_authorization_and_preserves_body() -> None:
    channel = _travelport_channel({"username": "assigned-user", "password": "assigned-pass"})
    root = _root("travelport/request.xml")
    before = serialize(root)
    headers = {
        "authorization": "Basic caller-lower",
        "Authorization": "Basic caller-title",
        "accept": "text/xml",
    }
    handler = get_handler(ChannelType.TRAVELPORT)

    assert handler.parse_operation(root) == "PingReq"
    assert handler.requires_body_inspection(channel) is False
    handler.swap_request_headers(_ctx(channel, headers))

    encoded = base64.b64encode(b"Universal API/assigned-user:assigned-pass").decode("ascii")
    assert headers == {"accept": "text/xml", "Authorization": f"Basic {encoded}"}
    assert handler.swap_request_body(root, _ctx(channel, headers)) is False
    assert serialize(root) == before


def test_travelport_disabled_credentials_are_noop() -> None:
    channel = ChannelConfig(
        name="travelport",
        type=ChannelType.TRAVELPORT,
        host="travelport.test",
        credentials={"username": "ignored-user", "password": "ignored-pass"},
    )
    headers = {"authorization": "Basic caller"}
    handler = get_handler(ChannelType.TRAVELPORT)

    handler.swap_request_headers(_ctx(channel, headers))

    assert headers == {"authorization": "Basic caller"}
    assert handler.requires_response_keyring(channel) is False


def test_travelport_request_header_swap_fails_closed_for_invalid_direct_config() -> None:
    handler = get_handler(ChannelType.TRAVELPORT)
    missing_password = _travelport_channel({"username": "assigned-user"})
    prefixed_username = _travelport_channel({"username": "Universal API/assigned-user", "password": "assigned-pass"})

    _assert_swap_error("missing credential password", handler.swap_request_headers, _ctx(missing_password, {}))
    _assert_swap_error("must not include the API prefix", handler.swap_request_headers, _ctx(prefixed_username, {}))


def test_travelport_encrypts_only_session_attributes() -> None:
    channel = _travelport_channel({"username": "assigned-user", "password": "assigned-pass"})
    keyring = Keyring.from_json(KEYRING_JSON)
    handler = get_handler(ChannelType.TRAVELPORT)
    response = _root("travelport/booking_start_response.xml")

    assert handler.requires_response_keyring(channel) is True
    assert handler.swap_response(response, SwapContext(channel, {}, keyring)) is True

    attrs = {
        etree.QName(element).localname: {etree.QName(name).localname: value for name, value in element.attrib.items()}
        for element in response.iter("*")
    }
    assert attrs["BookingStartRsp"]["SessionKey"].startswith("ENC_")
    assert attrs["Reference"]["id"] == "UNRELATED-ID-0001"

    session_request = _root("travelport/session_follow_up_request.xml")
    assert handler.swap_response(session_request, SwapContext(channel, {}, keyring)) is True
    session_attrs = {
        etree.QName(element).localname: {etree.QName(name).localname: value for name, value in element.attrib.items()}
        for element in session_request.iter("*")
    }
    assert session_attrs["SessTok"]["id"].startswith("ENC_")
    assert session_attrs["BookingTravelerReq"]["SessionKey"].startswith("ENC_")


def test_travelport_response_cleanup_is_idempotent_and_requires_keyring() -> None:
    channel = _travelport_channel({"username": "assigned-user", "password": "assigned-pass"})
    handler = get_handler(ChannelType.TRAVELPORT)
    already_encrypted = parse_bytes(
        b"<Envelope><BookingStartRsp SessionKey='ENC_aGVsbG8'/><SessTok id='ENC_aGVsbG8'/></Envelope>"
    )

    assert handler.swap_response(already_encrypted, SwapContext(channel, {}, Keyring.from_json(KEYRING_JSON))) is False
    _assert_swap_error(
        "response auth encryption requires keyring",
        handler.swap_response,
        _root("travelport/booking_start_response.xml"),
        _ctx(channel),
    )


def test_travelport_response_encryption_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _travelport_channel({"username": "assigned-user", "password": "assigned-pass"})
    keyring = Keyring.from_json(KEYRING_JSON)

    def fail_encrypt(_value: str, _keyring: Keyring) -> str:
        raise ValueError("synthetic crypto failure")

    monkeypatch.setattr("channel_relay.channels.handlers.encrypt", fail_encrypt)
    _assert_swap_error(
        "Travelport session encryption failed",
        get_handler(ChannelType.TRAVELPORT).swap_response,
        _root("travelport/booking_start_response.xml"),
        SwapContext(channel, {}, keyring),
    )


def test_sabre_session_reuse_request_is_not_recredentialed() -> None:
    # A Sabre request carrying a BinarySecurityToken (session reuse) must be left untouched so the
    # de-anonymized token reaches the channel; injecting a UsernameToken would open a new session.
    channel = _gds_channel(ChannelType.SABRE, {"soap_security": _SOAP_FRAGMENT})
    root = _root("sabre/request.xml")  # <Security><BinarySecurityToken>caller-token</...>
    handler = get_handler(ChannelType.SABRE)

    assert handler.parse_operation(root) == "TravelItineraryReadRQ"
    assert handler.swap_request_body(root, _ctx(channel)) is False

    xml = serialize(root).decode()
    assert "caller-token" in xml  # reused session token preserved
    assert "relay-token" not in xml  # not re-credentialed


def test_sabre_session_create_request_is_swapped() -> None:
    channel = _gds_channel(ChannelType.SABRE, {"soap_security": _SOAP_FRAGMENT})
    body = (
        b'<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/"'
        b' xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><soap-env:Header>'
        b"<wsse:Security><wsse:UsernameToken><wsse:Username>caller</wsse:Username>"
        b"</wsse:UsernameToken></wsse:Security></soap-env:Header>"
        b"<soap-env:Body><SessionCreateRQ/></soap-env:Body></soap-env:Envelope>"
    )
    handler = get_handler(ChannelType.SABRE)
    root = parse_bytes(body)

    assert handler.swap_request_body(root, _ctx(channel)) is True
    xml = serialize(root).decode()
    assert "relay-token" in xml
    assert "caller" not in xml


def test_soap_request_without_security_header_is_noop() -> None:
    channel = _gds_channel(ChannelType.SABRE, {"soap_security": _SOAP_FRAGMENT})
    handler = get_handler(ChannelType.SABRE)
    for body in (b"<Envelope/>", b"<Envelope><Header/><Body/></Envelope>"):
        assert handler.swap_request_body(parse_bytes(body), _ctx(channel)) is False


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
        ({"soap_security": "<Security><Token>"}, "parseable XML"),
    ],
    ids=["invalid-xpath", "invalid-fragment"],
)
def test_soap_security_swap_failures_fail_closed(credentials: dict[str, str], message: str) -> None:
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(credentials=credentials)

    _assert_swap_error(message, handler.swap_request_body, _root("amadeus/request.xml"), _ctx(channel))


@pytest.mark.parametrize(
    "target_xpath",
    ["string(//*)", "//*[local-name()='Missing']"],
    ids=["scalar-xpath", "missing-target"],
)
def test_soap_security_xpath_miss_without_username_token_is_noop(target_xpath: str) -> None:
    # A valid xpath that matches nothing on a credential-free (session-reuse) body is a no-op.
    handler = get_handler(ChannelType.SABRE)
    channel = _gds_channel(
        ChannelType.SABRE, {"soap_security": "<Security/>", "soap_security_target_xpath": target_xpath}
    )
    body = (
        b'<Envelope xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><Header>'
        b"<wsse:Security><wsse:BinarySecurityToken>t</wsse:BinarySecurityToken></wsse:Security>"
        b"</Header><Body/></Envelope>"
    )
    assert handler.swap_request_body(parse_bytes(body), _ctx(channel)) is False


def test_soap_security_xpath_miss_with_username_token_fails_closed() -> None:
    # The placeholder UsernameToken must never reach the supplier when the xpath target is missed.
    handler = get_handler(ChannelType.AMADEUS)
    channel = _gds_channel(
        credentials={"soap_security": "<Security/>", "soap_security_target_xpath": "//*[local-name()='Missing']"}
    )

    _assert_swap_error("UsernameToken", handler.swap_request_body, _root("amadeus/request.xml"), _ctx(channel))


def test_soap_security_with_both_tokens_fails_closed() -> None:
    # A Security element carrying both a session token and a placeholder UsernameToken is anomalous:
    # skipping would leak the placeholder, so the relay fails closed.
    handler = get_handler(ChannelType.SABRE)
    channel = _gds_channel(ChannelType.SABRE, {"soap_security": _SOAP_FRAGMENT})
    body = (
        b'<Envelope xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext"><Header>'
        b"<wsse:Security><wsse:BinarySecurityToken>t</wsse:BinarySecurityToken>"
        b"<wsse:UsernameToken><wsse:Username>caller</wsse:Username></wsse:UsernameToken>"
        b"</wsse:Security></Header><Body/></Envelope>"
    )
    _assert_swap_error("both", handler.swap_request_body, parse_bytes(body), _ctx(channel))


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


def test_amadeus_response_keeps_sequence_number_plaintext() -> None:
    keyring = Keyring.from_json(KEYRING_JSON)
    channel = _gds_channel(ChannelType.AMADEUS, {"soap_security": "<Security/>"})
    root = _root("amadeus/response_auth.xml")

    assert get_handler(ChannelType.AMADEUS).swap_response(
        root, SwapContext(channel=channel, headers={}, keyring=keyring)
    )

    fields = {node.tag.split("}")[-1]: node.text for node in root.iter("*")}
    assert fields["SessionId"] is not None and fields["SessionId"].startswith("ENC_")
    assert fields["SecurityToken"] is not None and fields["SecurityToken"].startswith("ENC_")
    # The conversation counter is left intact so the client can parse and increment it.
    assert fields["SequenceNumber"] == "42"


@pytest.mark.parametrize(
    ("credentials", "valid"),
    [
        ({"soap_security": "<Security/>"}, True),
        ({"soap_username": "u", "soap_password": "p"}, True),
        ({}, False),
        ({"soap_username": "u"}, False),
        ({"soap_security": "<Security/>", "soap_username": "u", "soap_password": "p"}, False),
        ({"soap_security": "<Security/>", "soap_username": "u"}, False),
    ],
    ids=["static", "dynamic", "neither", "incomplete-dynamic", "both", "static-plus-partial-dynamic"],
)
def test_soap_validate_credentials(credentials: dict[str, str], valid: bool) -> None:
    handler = get_handler(ChannelType.SABRE)
    channel = _gds_channel(ChannelType.SABRE, credentials)
    if valid:
        handler.validate_credentials(channel)
    else:
        with pytest.raises(ValueError, match="exactly one"):
            handler.validate_credentials(channel)


def test_soap_validate_credentials_noop_when_disabled() -> None:
    # credentials.enabled defaults False → no auth requirement even with no fields configured.
    channel = ChannelConfig(name="sabre", type=ChannelType.SABRE)
    get_handler(ChannelType.SABRE).validate_credentials(channel)


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
