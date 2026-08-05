"""Golden coverage for additional sample-confirmed Amadeus PII response shapes."""

from __future__ import annotations

import pytest
from tests.conftest import FIXTURES_DIR

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import deanonymize_request_body, parse_operation, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes

FIXTURES = FIXTURES_DIR / "amadeus"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _redact(name: str, ruleset: RuleSet, keyring: Keyring) -> tuple[bytes, dict[str, int]]:
    return redact_response_body(_fixture(name), channel="amadeus", ruleset=ruleset, keyring=keyring)


@pytest.mark.parametrize(
    ("fixture", "operation"),
    [
        ("extended_pnr_response.xml", "PNR_Reply"),
        ("sales_query_v10_response.xml", "SalesReports_DisplayQueryReportReply"),
        ("ticket_process_extended_response.xml", "Ticket_ProcessEDocReply"),
        ("ticket_process_concealed_extended_response.xml", "Ticket_ProcessEDocCCConcealedReply"),
        ("ticket_display_tst_payment_response.xml", "Ticket_DisplayTSTReply"),
        ("retrieve_tsm_passenger_response.xml", "Ticket_RetrieveListOfTSMReply"),
        ("sales_transaction_extended_response.xml", "SalesReports_DisplayTransactionReportReply"),
        ("queue_list_passenger_response.xml", "Queue_ListReply"),
        ("seat_map_passenger_response.xml", "Air_RetrieveSeatMapReply"),
        ("refund_init_passenger_response.xml", "AMA_TicketInitRefundRS"),
        ("refund_process_passenger_response.xml", "AMA_TicketProcessRefundRS"),
        ("pnr_history_contact_response.xml", "PNR_DisplayHistoryReply"),
    ],
)
def test_operation_from_body(fixture: str, operation: str) -> None:
    assert parse_operation(parse_bytes(_fixture(fixture))) == operation


def test_extended_pnr_typed_and_payment_fields_redacted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("extended_pnr_response.xml", baked_ruleset, pii_keyring)
    for value in (
        b"02021990",
        b"12 TEST STREET",
        b"411111XXXXXX1111",
        b"1229",
        b"HOTEL.CONTACT@EXAMPLE.COM",
        b"34 TEST AVENUE",
        b"ALICE BROWN",
        b"56 TEST ROAD",
        b"TESTVILLE",
        b"15550000002",
        b"15550000003",
    ):
        assert value not in redacted
    assert counts["dob"] == 2
    assert counts["address"] == 6
    assert counts["payment"] == 2
    assert counts["email"] == 1 and counts["phone"] == 2
    assert b"PNR001" in redacted


@pytest.mark.parametrize(
    ("fixture", "plaintext", "operational"),
    [
        ("sales_query_v10_response.xml", b"BROWN/ALICE MS", b"1720000000000"),
        ("retrieve_tsm_passenger_response.xml", b"BROWN", b"<passengerReference>1</passengerReference>"),
        ("queue_list_passenger_response.xml", b"BROWN", b"PNR002"),
        ("seat_map_passenger_response.xml", b"BROWN", b"<cabinClassDesignator>Y</cabinClassDesignator>"),
        ("refund_init_passenger_response.xml", b"BROWN", b"1720000000000"),
        ("refund_process_passenger_response.xml", b"GREEN", b"1720000000001"),
    ],
)
def test_passenger_names_encrypt_and_operational_data_survives(
    fixture: str, plaintext: bytes, operational: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    redacted, counts = _redact(fixture, baked_ruleset, pii_keyring)
    assert plaintext not in redacted
    assert counts["person"] >= 1
    assert operational in redacted
    restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert plaintext in restored


@pytest.mark.parametrize(
    ("fixture", "name", "ff", "document"),
    [
        ("ticket_process_extended_response.xml", b"BROWN", b"FF000001", b"1720000000000"),
        ("ticket_process_concealed_extended_response.xml", b"GREEN", b"FF000002", b"1720000000001"),
    ],
)
def test_ticket_names_loyalty_and_payment_redacted(
    fixture: str, name: bytes, ff: bytes, document: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    redacted, counts = _redact(fixture, baked_ruleset, pii_keyring)
    for value in (name, ff, b"XXXXXX", b"1229", b"1130", b"ABC123", b"DEF456"):
        assert value not in redacted
    assert counts["person"] == 2
    assert counts["frequent_flyer"] == 1
    assert counts["payment"] == 3
    assert document in redacted
    restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert name in restored and ff in restored


def test_ticket_display_payment_redacted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("ticket_display_tst_payment_response.xml", baked_ruleset, pii_keyring)
    assert b"411111XXXXXX1111" not in redacted
    assert counts == {"payment": 1}


def test_sales_transaction_names_and_payment_redacted(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("sales_transaction_extended_response.xml", baked_ruleset, pii_keyring)
    for value in (b"BROWN/ALICE MS", b"411111XXXXXX1111", b"1229", b"ABC123"):
        assert value not in redacted
    assert counts == {"person": 1, "payment": 3}
    assert b"1720000000000" in redacted


def test_history_email_span_redacted_and_note_preserved(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact("pnr_history_contact_response.xml", baked_ruleset, pii_keyring)
    assert b"TEST.USER@EXAMPLE.COM" not in redacted
    assert counts == {"email": 1}
    assert b"CONTACT " in redacted and b" RETAIN NOTE" in redacted and b"PNR003" in redacted


def test_encrypted_sales_name_is_reversible(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, _ = _redact("sales_query_v10_response.xml", baked_ruleset, pii_keyring)
    root = parse_bytes(redacted)
    names = root.xpath("//*[local-name()='surname']/text()")
    assert len(names) == 1 and TOKEN_RE.fullmatch(str(names[0]))
    assert decrypt(str(names[0]), pii_keyring) == "BROWN/ALICE MS"
