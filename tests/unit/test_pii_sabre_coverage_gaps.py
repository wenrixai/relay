"""Golden coverage for additional sample- and schema-confirmed Sabre PII shapes."""

from __future__ import annotations

from tests.conftest import FIXTURES_DIR

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import deanonymize_request_body, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes

FIXTURES = FIXTURES_DIR / "sabre"


def _redact(name: str, ruleset: RuleSet, keyring: Keyring) -> tuple[bytes, dict[str, int]]:
    body = (FIXTURES / name).read_bytes()
    return redact_response_body(body, channel="sabre", ruleset=ruleset, keyring=keyring)


def test_update_reservation_mirrors_redacted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("update_reservation_pii_response.xml", baked_ruleset, pii_keyring)
    for value in (b"BROWN", b"ALICE", b"TEST.USER@EXAMPLE.COM", b"15550000001", b"1990-02-02", b"02FEB1990"):
        assert value not in redacted
    assert counts["person"] >= 6
    assert counts["email"] == 1 and counts["phone"] == 1
    assert counts["dob"] == 2 and counts["gender"] == 2
    assert b"PNR004" in redacted


def test_air_ticket_v121_names_encrypt(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("air_ticket_v121_response.xml", baked_ruleset, pii_keyring)
    assert b"ALICE" not in redacted and b"BROWN" not in redacted
    assert counts == {"person": 2}
    assert b"1720000000000" in redacted


def test_get_reservation_variants_redacted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("get_reservation_variant_response.xml", baked_ruleset, pii_keyring)
    assert b"2015-03-04" not in redacted and b'expiryDate="1229"' not in redacted
    assert counts["person"] >= 6 and counts["dob"] == 1 and counts["payment"] == 2
    root = parse_bytes(redacted)
    assert root.xpath("string(//*[local-name()='ChildRequest']/*[local-name()='DateOfBirth'])") == "1900-01-01"
    assert root.xpath("string(//*[local-name()='Card']/@expiryDate)") == "0000"
    assert b"PNR005" in redacted


def test_edoc_loyalty_and_masked_card_redacted_and_round_trip(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("edoc_extended_response.xml", baked_ruleset, pii_keyring)
    assert b"FF000001" not in redacted and b"411111XXXXXX1111" not in redacted
    assert counts["frequent_flyer"] == 1 and counts["payment"] == 1
    restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert b"FF000001" in restored
    assert b"1720000000000" in redacted


def test_ticket_document_masked_card_redacted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("ticket_document_extended_response.xml", baked_ruleset, pii_keyring)
    assert b"555555XXXXXX4444" not in redacted
    assert counts["payment"] == 1
    assert b"1720000000001" in redacted


def test_itinerary_history_accounting_name_encrypted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("travel_itinerary_history_accounting_response.xml", baked_ruleset, pii_keyring)
    root = parse_bytes(redacted)
    value = root.xpath("string(//*[local-name()='AccountingInfo']/*[local-name()='PersonName'])")
    assert TOKEN_RE.fullmatch(value)
    assert decrypt(value, pii_keyring) == "BROWN/ALICE"
    assert counts["person"] >= 2
    assert b"1720000000000" in redacted


def test_create_pnr_customer_response_redacted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("create_pnr_customer_response.xml", baked_ruleset, pii_keyring)
    for value in (
        b"ALICE",
        b"BROWN",
        b"TEST.USER@EXAMPLE.COM",
        b"15550000001",
        b"12 TEST STREET",
        b"FF000001",
        b"P0000001",
    ):
        assert value not in redacted
    assert counts == {"person": 4, "email": 1, "phone": 2, "address": 2, "frequent_flyer": 1, "passport_id": 1}
    assert b"PNR006" in redacted
