"""Golden redaction tests for the baked Travelport (UAPI) baseline rules."""

from __future__ import annotations

from channel_relay.channels import get_handler
from channel_relay.config.models import ChannelType
from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import deanonymize_request_body, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

TRAVELPORT_FIXTURES = FIXTURES_DIR / "travelport"


def _fixture(name: str) -> bytes:
    return (TRAVELPORT_FIXTURES / name).read_bytes()


def _redact(body: bytes, ruleset: RuleSet, keyring: Keyring) -> tuple[bytes, dict[str, int]]:
    return redact_response_body(
        body,
        channel="travelport",
        ruleset=ruleset,
        keyring=keyring,
        operation_parser=get_handler(ChannelType.TRAVELPORT).parse_operation,
    )


def test_operation_parser_uses_soap_body_child() -> None:
    handler = get_handler(ChannelType.TRAVELPORT)

    assert (
        handler.parse_operation(parse_bytes(_fixture("universal_record_retrieve_response.xml")))
        == "UniversalRecordRetrieveRsp"
    )
    assert handler.parse_operation(parse_bytes(_fixture("terminal_display_response.xml"))) == "TerminalRsp"


def test_universal_record_redacts_every_pii_surface(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact(_fixture("universal_record_retrieve_response.xml"), baked_ruleset, pii_keyring)

    assert counts == {
        "person": 10,
        "email": 2,
        "phone": 3,
        "dob": 2,
        "gender": 1,
        "frequent_flyer": 1,
        "address": 3,
        "payment": 2,
        "visa": 3,
    }
    for gone in (
        b"JOHN",
        b"SMITH",
        b"JANE",
        b"DOE",
        b"john.smith@example.test",
        b"14155550100",
        b"14155550199",
        b"AB123456",
        b"100 TEST STREET",
        b"TESTVILLE",
        b">00000<",
        b"************1234",
        b"2030-12",
        b"1980-01-15",
        b'Gender="F"',
        b"1/US/123456789/US/15JAN80/M/01JAN30/SMITH/JOHN",
        b"1/123456789/US/15JAN80/M",
        b"USHK1/NI123456789-001.01",
        b"1/john.smith@example.test",
        b"/REFUSED TO PROVIDE-1DOE/JANE",
        b"DOE/J MISS DOB",
        b"DOB 15JAN20",
    ):
        assert gone not in redacted, gone

    # non-PII survives verbatim: locators, ticket number, agent/PCC codes, geo codes, remark shell
    for kept in (
        b"TESTAA",
        b"TESTBB",
        b"TESTCC",
        b"TESTDD",
        b"TESTEE",
        b"0991234567890",
        b"0991234567890C1",
        b'OwningPCC="TST"',
        b">CA<",
        b">US<",
        b"SNC RLOC AA TESTBB",
        b"PASSENGER",
        b"CONTACT CONFIRMED",
    ):
        assert kept in redacted, kept

    restored, decrypted = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert decrypted == 10
    assert b"JOHN" in restored
    assert b"SMITH" in restored
    assert b"john.smith@example.test" in restored
    assert b"AB123456" in restored
    # mask/replace/remove are one-way: they never restore
    assert b"100 TEST STREET" not in restored
    assert b"1980-01-15" not in restored


def test_dob_and_gender_are_type_valid_after_redaction(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, _ = _redact(_fixture("universal_record_retrieve_response.xml"), baked_ruleset, pii_keyring)

    assert b'DOB="1900-01-01"' in redacted
    # Gender is replaced with the fixed valid code rather than dropped, so the attribute stays
    # present and schema-valid for the caller — one convention across every channel.
    assert b'Gender="M"' in redacted


def test_credit_card_masked_not_tokenized(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, _ = _redact(_fixture("universal_record_retrieve_response.xml"), baked_ruleset, pii_keyring)

    assert b'Number="REDACTED"' in redacted
    assert b'ExpDate="0000000"' in redacted
    assert b"ENC_" not in redacted.split(b"CreditCard")[1].split(b"/>")[0]


def test_terminal_screen_names_masked(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact(_fixture("terminal_display_response.xml"), baked_ruleset, pii_keyring)

    assert counts == {"person": 3}
    for gone in (b"SMITH/JOHN", b"DOE/JANEMISS", b"1.1SMITH", b"2.1DOE"):
        assert gone not in redacted
    # the ticket number and GDS codes on the same screen are not PII and survive
    for kept in (b"0991234567890", b"TESTAA", b"TESTBB", b"TST"):
        assert kept in redacted
    assert b"ENC_" not in redacted  # terminal names are masked (one-way), never ENC_ tokens


def test_unknown_travelport_operation_passes_through(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    # Travelport's rule bundle matches any operation ending in "Rsp" (the whole UAPI schema
    # reuses the same common:BookingTraveler/etc. fragments regardless of operation), so a
    # true pass-through case is an operation name that doesn't end in "Rsp" at all.
    body = b"<Envelope><Body><Fault><Name First='JOHN' Last='SMITH'/></Fault></Body></Envelope>"

    redacted, counts = _redact(body, baked_ruleset, pii_keyring)

    assert counts == {}
    assert b"JOHN" in redacted and b"SMITH" in redacted


def test_ruleset_version_covers_travelport(baked_ruleset: RuleSet) -> None:
    assert any(rule.channel == "travelport" for rule in baked_ruleset.rules)
    assert "travelport" in baked_ruleset.rules_version


def test_reference_rule_redacts_name_echoed_in_general_remark(
    baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    redacted, _ = _redact(_fixture("universal_record_retrieve_response.xml"), baked_ruleset, pii_keyring)

    (remark_text,) = xml_texts(redacted, "RemarkData")
    assert remark_text.startswith("PASSENGER ENC_")
    assert remark_text.endswith("CONTACT CONFIRMED")
    token = remark_text.removeprefix("PASSENGER ").removesuffix(" CONTACT CONFIRMED")
    assert TOKEN_RE.fullmatch(token)
    assert decrypt(token, pii_keyring) == "SMITH"
