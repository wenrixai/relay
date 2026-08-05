"""Golden redaction tests for the baked Travelfusion baseline rules."""

from __future__ import annotations

from channel_relay.channels import get_handler
from channel_relay.config.models import ChannelType
from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import deanonymize_request_body, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

TRAVELFUSION_FIXTURES = FIXTURES_DIR / "travelfusion"


def _fixture(name: str) -> bytes:
    return (TRAVELFUSION_FIXTURES / name).read_bytes()


def _redact(body: bytes, ruleset: RuleSet, keyring: Keyring) -> tuple[bytes, dict[str, int]]:
    return redact_response_body(
        body,
        channel="travelfusion",
        ruleset=ruleset,
        keyring=keyring,
        operation_parser=get_handler(ChannelType.TRAVELFUSION).parse_operation,
    )


def _xpath_texts(body: bytes, path: str) -> list[str]:
    root = parse_bytes(body)
    return [node.text or "" for node in root.xpath(path)]


def test_operation_parser_uses_travelfusion_command_child() -> None:
    handler = get_handler(ChannelType.TRAVELFUSION)

    assert handler.parse_operation(parse_bytes(_fixture("get_booking_details_response.xml"))) == "GetBookingDetails"
    assert (
        handler.parse_operation(parse_bytes(_fixture("get_latest_booking_details_response.xml")))
        == "GetLatestBookingDetails"
    )


def test_booking_profile_names_email_and_address_redacted(
    baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    redacted, counts = _redact(_fixture("get_booking_details_response.xml"), baked_ruleset, pii_keyring)

    assert counts == {
        "person": 20,
        "gender": 4,
        "age": 2,
        "dob": 2,
        "email": 1,
        "phone": 7,
        "address": 9,
        "ip_address": 1,
    }
    for gone in (
        b"ALEX",
        b"CASEY",
        b"BROWN",
        b"MORGAN",
        b"STONE",
        b"traveler@example.test",
        b"100 TEST STREET",
        b"TESTVILLE",
        b"Ticket number for MR ALEX",
        b"21/11/1985",
        b"26/11/1986",
        b"<Age>35</Age>",
        b"<Age>36</Age>",
        b"<Title>Mr</Title>",
        b"<InternationalCode>33</InternationalCode>",
        b"<AreaCode>1</AreaCode>",
        b"<Number>123456</Number>",
        b"<InternationalCode>44</InternationalCode>",
        b"<AreaCode>20</AreaCode>",
        b"<Number>70001112</Number>",
        b"<Extension>9</Extension>",
        b"84.110.102.10",
    ):
        assert gone not in redacted

    name_parts = xml_texts(redacted, "NamePart")
    encrypted_names = [value for value in name_parts if TOKEN_RE.fullmatch(value)]
    assert len(encrypted_names) == 8
    assert {decrypt(token, pii_keyring) for token in encrypted_names} == {
        "ALEX",
        "BROWN",
        "CASEY",
        "MORGAN",
        "STONE",
    }
    (email_token,) = xml_texts(redacted, "Email")
    assert TOKEN_RE.fullmatch(email_token)
    assert decrypt(email_token, pii_keyring) == "traveler@example.test"
    street_tokens = _xpath_texts(
        redacted, "//*[local-name()='BookingProfile']//*[local-name()='Address']/*[local-name()='Street']"
    )
    assert street_tokens and all(TOKEN_RE.fullmatch(value) for value in street_tokens)
    assert {decrypt(token, pii_keyring) for token in street_tokens} == {"100 TEST STREET"}

    root = parse_bytes(redacted)
    phone_leaves = root.xpath(
        "//*[local-name()='BookingProfile']/*[local-name()='ContactDetails']"
        "/*[local-name()='HomePhone' or local-name()='WorkPhone' or local-name()='MobilePhone' or local-name()='Fax']/*"
    )
    populated_phone_values = [node.text for node in phone_leaves if node.text]
    assert populated_phone_values and all(TOKEN_RE.fullmatch(value) for value in populated_phone_values)
    phone_containers = root.xpath(
        "//*[local-name()='BookingProfile']/*[local-name()='ContactDetails']"
        "/*[local-name()='HomePhone' or local-name()='WorkPhone' or local-name()='MobilePhone' or local-name()='Fax']"
    )
    assert all(not (node.text or "").strip() for node in phone_containers)

    restored, decrypted = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert decrypted == 46
    assert b"ALEX" in restored and b"traveler@example.test" in restored and b"100 TEST STREET" in restored
    assert b"21/11/1985" in restored and b"70001112" in restored and b"84.110.102.10" in restored


def test_payment_profile_encrypts_card_data(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact(_fixture("get_booking_details_payment_response.xml"), baked_ruleset, pii_keyring)

    assert counts == {
        "person": 10,
        "gender": 3,
        "age": 1,
        "dob": 1,
        "frequent_flyer": 1,
        "passport_id": 2,
        "nationality": 2,
        "email": 1,
        "phone": 7,
        "address": 7,
        "payment": 4,
    }
    for gone in (
        b"4111111111111111",
        b"<SecurityCode>123</SecurityCode>",
        b"<ExpiryDate>12/30</ExpiryDate>",
        b"<StartDate>01/25</StartDate>",
        b"<IssueNumber>7</IssueNumber>",
        b"billing@example.test",
        b"12/05/1234",
        b"FF00012345",
        b"31/12/2030",
        b">XZ<",
        b">YZ<",
        b"P00012345",
        b"<Age>20</Age>",
        b"<Title>Ms</Title>",
        b"<InternationalCode>435r</InternationalCode>",
        b"<Number>fsdfdsf</Number>",
    ):
        assert gone not in redacted
    for local_name in ("Number", "SecurityCode", "ExpiryDate", "StartDate"):
        values = _xpath_texts(
            redacted,
            "//*[local-name()='BookingProfile']/*[local-name()='BillingDetails']"
            f"/*[local-name()='CreditCard']/*[local-name()='{local_name}']",
        )
        assert values and all(TOKEN_RE.fullmatch(value) for value in values), local_name
    root = parse_bytes(redacted)
    sensitive_parameter_values = root.xpath(
        "//*[local-name()='BookingProfile']//*[local-name()='CustomSupplierParameter']"
        "[*[local-name()='Name']='DateOfBirth' or *[local-name()='Name']='FrequentFlyerNumber' or "
        "*[local-name()='Name']='PassportExpiryDate' or *[local-name()='Name']='CountryOfResidence' or "
        "*[local-name()='Name']='PassportCountryOfIssue' or *[local-name()='Name']='PassportNumber']"
        "/*[local-name()='Value']/text()"
    )
    assert sensitive_parameter_values and all(TOKEN_RE.fullmatch(value) for value in sensitive_parameter_values)
    assert {decrypt(value, pii_keyring) for value in sensitive_parameter_values} == {
        "12/05/1234",
        "FF00012345",
        "31/12/2030",
        "XZ",
        "YZ",
        "P00012345",
    }
    assert b"MasterCard" in redacted


def test_latest_booking_names_redact_and_operational_fields_survive(
    baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    redacted, counts = _redact(_fixture("get_latest_booking_details_response.xml"), baked_ruleset, pii_keyring)

    assert counts == {"person": 8, "gender": 2, "dob": 2, "ip_address": 1}
    assert b"ALEX" not in redacted and b"CASEY" not in redacted and b"BROWN" not in redacted
    assert b"Ticket number for MRS CASEY" not in redacted
    assert b"01/01/1900" not in redacted and b"02/02/1900" not in redacted
    assert b"<Title>MRS</Title>" not in redacted
    assert b"84.110.102.10" not in redacted
    for kept in (b"POA227", b"Ticketed", b"1533.94", b"EUR"):
        assert kept in redacted


def test_unknown_travelfusion_operation_passes_through(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    body = b"<CommandList><Unknown><NamePart>ALEX</NamePart></Unknown></CommandList>"

    redacted, counts = _redact(body, baked_ruleset, pii_keyring)

    assert counts == {}
    assert b"<NamePart>ALEX</NamePart>" in redacted


def test_ruleset_version_covers_travelfusion(baked_ruleset: RuleSet) -> None:
    assert any(rule.channel == "travelfusion" for rule in baked_ruleset.rules)
    assert "travelfusion" in baked_ruleset.rules_version
