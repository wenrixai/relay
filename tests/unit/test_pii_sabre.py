"""Golden redaction tests for the baked Sabre baseline rules (rules_fallback.json).

One sanitized fixture per covered operation. Names/emails/frequent-flyer numbers are
encrypted (reversible ``ENC_`` tokens) — including Sabre's attribute-borne names; contact,
identity-document (DOCS/DOCO), and payment fields are masked (one-way). Operational data
(locators, ticket numbers, amounts, agent sines) is preserved verbatim.

Shared golden fixtures (``pii_keyring``, ``baked_ruleset``, ``xml_texts``) live in
``tests/conftest.py``.
"""

from __future__ import annotations

import re

import pytest

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import (
    RedactionError,
    deanonymize_request_body,
    parse_operation,
    redact_response,
    redact_response_body,
)
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

SABRE_FIXTURES = FIXTURES_DIR / "sabre"
_MASKED_RE = re.compile(r"^\*+$")


def _fixture(name: str) -> bytes:
    return (SABRE_FIXTURES / name).read_bytes()


def _redact(body: bytes, ruleset: RuleSet, keyring: Keyring) -> tuple[bytes, dict[str, int]]:
    return redact_response_body(body, channel="sabre", ruleset=ruleset, keyring=keyring)


def _attrs(body: bytes, attr_name: str) -> list[str]:
    root = parse_bytes(body)
    result = root.xpath(f"//@*[local-name()='{attr_name}']")
    assert isinstance(result, list)
    return [str(value) for value in result]


class TestGetPriceQuote:
    """GetPriceQuoteRS: names live in attributes; payment data in the PQR variant."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("get_price_quote_response.xml"))) == "GetPriceQuoteRS"

    def test_name_attributes_encrypt_and_round_trip(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("get_price_quote_response.xml"), baked_ruleset, pii_keyring)
        assert b"TESTMSTR" not in redacted and b"MARY" not in redacted
        first_names = _attrs(redacted, "firstName")
        last_names = _attrs(redacted, "lastName")
        assert first_names and last_names
        for token in [*first_names, *last_names]:
            assert TOKEN_RE.fullmatch(token)
        decrypted_first = {decrypt(token, pii_keyring) for token in first_names}
        assert decrypted_first == {"TESTMSTR", "MARY"}
        assert {decrypt(token, pii_keyring) for token in last_names} == {"TEST"}
        assert counts["person"] == len(first_names) + len(last_names)
        # Attribute tokens de-anonymize on the way back upstream.
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"TESTMSTR" in restored and b"MARY" in restored

    def test_pqr_payment_masked(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("get_price_quote_pqr_response.xml"), baked_ruleset, pii_keyring)
        # Supplier-masked card number is still rewritten; BIN gone from element and free text.
        assert b"XXXXXXXXXXXX0000" not in redacted
        assert b"411111" not in redacted
        assert counts["payment"] >= 3  # card @number + BIN element + BIN span in description
        # The BIN extraction preserves the surrounding description text.
        assert b"CC NBR BEGINS WITH" in redacted

    def test_pqr_names_in_exchange_doc_encrypted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_price_quote_pqr_response.xml"), baked_ruleset, pii_keyring)
        assert b"DOE JANE MS" not in redacted
        assert all(TOKEN_RE.fullmatch(value) for value in _attrs(redacted, "firstName"))
        assert all(TOKEN_RE.fullmatch(value) for value in _attrs(redacted, "lastName"))

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_price_quote_pqr_response.xml"), baked_ruleset, pii_keyring)
        assert b"ABCDEF" in redacted  # record locator
        assert b'number="1575590599399"' in redacted  # exchange document number
        root = parse_bytes(redacted)
        sines = root.xpath("//@sine")
        assert isinstance(sines, list) and "AWS" in [str(s) for s in sines]


class TestAirTicket:
    """AirTicketRS (EMD): names as element text in the Summary block."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("air_ticket_emd_response.xml"))) == "AirTicketRS"

    def test_names_encrypt_and_round_trip(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, counts = _redact(_fixture("air_ticket_emd_response.xml"), baked_ruleset, pii_keyring)
        assert counts == {"person": 2}
        (first,) = xml_texts(redacted, "FirstName")
        (last,) = xml_texts(redacted, "LastName")
        assert TOKEN_RE.fullmatch(first) and TOKEN_RE.fullmatch(last)
        assert decrypt(first, pii_keyring) == "JOHN"
        assert decrypt(last, pii_keyring) == "DOE"

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
        redacted, _ = _redact(_fixture("air_ticket_emd_response.xml"), baked_ruleset, pii_keyring)
        assert xml_texts(redacted, "DocumentNumber") == ["1142837817060"]
        assert xml_texts(redacted, "Reservation") == ["TESTBB"]
        assert b"356.81" in redacted


class TestRequiredAnchorsFailClosed:
    """Each PII-heavy Sabre op has a required passenger-name anchor: drift → RedactionError (502).

    An anchor that locates no nodes (schema rename on a version bump) must fail closed rather
    than forward an unredacted response (fix-sabre-anchor-rules-required, sabre-pii-baseline spec).
    """

    @pytest.mark.parametrize(
        "body",
        [
            b'<AirTicketRS xmlns="http://services.sabre.com/sp/air/ticket/v1"/>',
            b'<DailySalesReportRS xmlns="http://webservices.sabre.com/sabreXML/2011/10"/>',
            b'<TravelItineraryReadRS xmlns="http://services.sabre.com/res/tir/v3_10"/>',
            b'<GetPriceQuoteRS xmlns="http://www.sabre.com/ns/Ticketing/pqs/1.0"/>',
        ],
        ids=["AirTicketRS", "DailySalesReportRS", "TravelItineraryReadRS", "GetPriceQuoteRS"],
    )
    def test_missing_anchor_fails_closed(self, body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        with pytest.raises(RedactionError):
            _redact(body, baked_ruleset, pii_keyring)

    def test_normal_fixtures_still_redact(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # The anchors must match on the real fixtures (no false 502).
        for fixture in (
            "air_ticket_emd_response.xml",
            "daily_sales_report_response.xml",
            "travel_itinerary_read_response.xml",
            "get_price_quote_response.xml",
        ):
            _, counts = _redact(_fixture(fixture), baked_ruleset, pii_keyring)
            assert counts.get("person", 0) >= 1


class TestUncoveredOperation:
    """A Sabre operation without baseline rules passes through unchanged."""

    def test_no_rules_no_rewrite(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        body = (
            b'<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">'
            b"<soap-env:Body><UnknownRS><Name>JOHN</Name></UnknownRS></soap-env:Body></soap-env:Envelope>"
        )
        redacted, counts = _redact(body, baked_ruleset, pii_keyring)
        assert counts == {}
        assert b"<Name>JOHN</Name>" in redacted


class TestGetReservation:
    """GetReservationRS: names/email/FF encrypted; contact, DOCS/DOCO, payment masked."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("get_reservation_response.xml"))) == "GetReservationRS"

    def test_names_encrypt_everywhere_and_round_trip(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, _ = _redact(_fixture("get_reservation_response.xml"), baked_ruleset, pii_keyring)
        # Passenger element text and the embedded pqs PriceQuoteInfo name attributes are all gone.
        for gone in (b"BROWN", b"DANA MS", b"DAN MR"):
            assert gone not in redacted
        last_names = xml_texts(redacted, "LastName")
        assert last_names and all(TOKEN_RE.fullmatch(name) for name in last_names)
        assert {decrypt(name, pii_keyring) for name in last_names} == {"BROWN"}
        assert all(TOKEN_RE.fullmatch(value) for value in _attrs(redacted, "firstName"))
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"BROWN" in restored and b"DANA MS" in restored

    def test_phone_masked_one_way(self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
        redacted, counts = _redact(_fixture("get_reservation_response.xml"), baked_ruleset, pii_keyring)
        assert b"TESTA ISB" not in redacted
        assert counts["phone"] == 1
        numbers = [t for t in xml_texts(redacted, "Number") if _MASKED_RE.fullmatch(t)]
        assert len(numbers) == 1

    def test_history_fixture_full_coverage(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, counts = _redact(_fixture("get_reservation_pq_history_response.xml"), baked_ruleset, pii_keyring)
        # Every planted PII value is gone: email, FF number, DOB (both formats), DOCO
        # document number, phones, address street/city, card number.
        for gone in (
            b"SUPPLIER-CONTACT@ACMEX.COM",
            b"SUPPLIER-CONTACT@TESTAGENCY.COM",
            b"<stl19:Number>0000000000<",
            b"<or114:FrequentFlyerNumber>0000000000<",
            b"1990-01-01",
            b"01JAN1990",
            b"TT00TEST0",
            b"800-555-0100",
            b"5555550100",
            b"1234 MAIN TEST RD",
            b"TEST CITY CA 00000",
            b"4XXXXXXXXXXX0000",
        ):
            assert gone not in redacted
        # Emails and FF numbers are reversible; DOCS/DOCO and payment are one-way masks.
        addresses = [t for t in xml_texts(redacted, "Address") if t.strip()]
        assert addresses and all(TOKEN_RE.fullmatch(a) for a in addresses)
        assert {decrypt(a, pii_keyring) for a in addresses} == {
            "SUPPLIER-CONTACT@ACMEX.COM",
            "SUPPLIER-CONTACT@TESTAGENCY.COM",
        }
        for masked_local in ("CardNumber", "DocumentNumber"):
            values = [t for t in xml_texts(redacted, masked_local) if t]
            assert values and all(_MASKED_RE.fullmatch(v) for v in values), masked_local
        # DateOfBirth is a typed field: one-way replaced with a schema-valid ISO sentinel
        # (never a ``*`` mask that would crash the caller's date parser).
        dobs = [t for t in xml_texts(redacted, "DateOfBirth") if t]
        assert dobs and all(v == "1901-01-01" for v in dobs)
        assert counts["visa"] >= 3  # DOCO entry + or114 DOCO/DOCS free-text lines

    def test_name_echo_in_ticket_free_text_referenced(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        # The passenger name collected from PassengerName is also encrypted where it is echoed
        # inside e-ticket free-text lines, while the surrounding operational text survives.
        redacted, _ = _redact(_fixture("get_reservation_pq_history_response.xml"), baked_ruleset, pii_keyring)
        assert b"TESTR/T" not in redacted
        echoes = [t for t in xml_texts(redacted, "OriginalTicketDetails") if t.strip()]
        assert echoes
        for echo in echoes:
            assert "TE 0067890261595-AT" in echo  # operational prefix preserved
            assert "ENC_" in echo

    def test_history_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_reservation_pq_history_response.xml"), baked_ruleset, pii_keyring)
        for kept in (
            b"TESTBC",  # record locator
            b"0067890261595",  # ticket number
            b"33A",  # seat
            b"010226",  # DK number
            b"ATL",  # segment data
        ):
            assert kept in redacted


class TestDailySalesReport:
    """DailySalesReportRS: slash-format PersonName per issuance record."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("daily_sales_report_response.xml"))) == "DailySalesReportRS"

    def test_person_names_encrypt_and_round_trip(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, counts = _redact(_fixture("daily_sales_report_response.xml"), baked_ruleset, pii_keyring)
        assert counts == {"person": 6}
        names = xml_texts(redacted, "PersonName")
        assert len(names) == 6
        assert all(TOKEN_RE.fullmatch(name) for name in names)
        decrypted = {decrypt(name, pii_keyring) for name in names}
        assert "TESTONE/ALICE" in decrypted and "TESTFIVE/EVE" in decrypted
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"TESTTWO/BOB MR" in restored

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("daily_sales_report_response.xml"), baked_ruleset, pii_keyring)
        for kept in (b"0067669041160", b"5140676", b"EXAMPLE TRAVEL AGENCY", b"34D1"):
            assert kept in redacted


class TestTravelItinerary:
    """TravelItineraryReadRS: PassengerData carries SURNAME/GIVEN when unredacted upstream."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("travel_itinerary_read_response.xml"))) == "TravelItineraryReadRS"

    def test_passenger_data_encrypted(self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
        redacted, counts = _redact(_fixture("travel_itinerary_read_response.xml"), baked_ruleset, pii_keyring)
        names = xml_texts(redacted, "PassengerData")
        assert names and all(TOKEN_RE.fullmatch(name) for name in names)
        assert "XXXXXX/XXXXXX MR" in {decrypt(name, pii_keyring) for name in names}
        assert counts["person"] == len(names)
        # Corporate/tour identifiers are operational, not PII.
        assert b"GEC01" in redacted and b"GENELEC" in redacted


class TestTicketRefund:
    """RefundRS (bare root op): passenger names in Traveler attributes."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("ticket_refund_response.xml"))) == "RefundRS"

    def test_names_encrypt_and_round_trip(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("ticket_refund_response.xml"), baked_ruleset, pii_keyring)
        assert counts == {"person": 2}
        assert b"MILLER" not in redacted and b"ROBERT" not in redacted
        (last,) = _attrs(redacted, "lastName")
        (first,) = _attrs(redacted, "firstName")
        assert TOKEN_RE.fullmatch(last) and TOKEN_RE.fullmatch(first)
        assert decrypt(last, pii_keyring) == "MILLER"
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"MILLER" in restored

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("ticket_refund_response.xml"), baked_ruleset, pii_keyring)
        assert b"TBSFWO" in redacted and b"0019122261730" in redacted


class TestDailyRefundReport:
    """DailyRefundReportRS: slash-format PersonName per refund record."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("daily_refund_report_response.xml"))) == "DailyRefundReportRS"

    def test_names_encrypt(self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
        redacted, counts = _redact(_fixture("daily_refund_report_response.xml"), baked_ruleset, pii_keyring)
        assert counts == {"person": 5}
        names = xml_texts(redacted, "PersonName")
        assert len(names) == 5 and all(TOKEN_RE.fullmatch(n) for n in names)

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("daily_refund_report_response.xml"), baked_ruleset, pii_keyring)
        assert b"KIWETP" in redacted and b"AAG" in redacted


class TestETicketCoupon:
    """eTicketCouponRS: names (element text); FOP/card fields masked. Covers exchange variant too."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("eticket_coupon_response.xml"))) == "eTicketCouponRS"
        assert parse_operation(parse_bytes(_fixture("ticket_exchange_response.xml"))) == "eTicketCouponRS"

    def test_names_encrypt_and_round_trip(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, counts = _redact(_fixture("eticket_coupon_response.xml"), baked_ruleset, pii_keyring)
        assert b"BENNETT" not in redacted and b"ROBERTALICIA" not in redacted
        (surname,) = xml_texts(redacted, "Surname")
        assert TOKEN_RE.fullmatch(surname) and decrypt(surname, pii_keyring) == "BENNETT"
        assert counts["person"] >= 2

    def test_exchange_variant_names_and_payment_redacted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("ticket_exchange_response.xml"), baked_ruleset, pii_keyring)
        assert b"GARCIA" not in redacted and b"MARIA" not in redacted
        assert counts["person"] == 2 and counts["payment"] >= 3
        assert b"XDDPQO" in redacted  # locator preserved


class TestGetElectronicDocument:
    """GetElectronicDocumentRS: ticket passenger name + external document number."""

    def test_operation(self) -> None:
        op = parse_operation(parse_bytes(_fixture("get_electronic_document_response.xml")))
        assert op == "GetElectronicDocumentRS"

    def test_name_encrypt_document_masked(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, counts = _redact(_fixture("get_electronic_document_response.xml"), baked_ruleset, pii_keyring)
        assert b"COHEN" not in redacted and b"D9002000" not in redacted
        (last,) = xml_texts(redacted, "LastName")
        assert TOKEN_RE.fullmatch(last) and decrypt(last, pii_keyring) == "COHEN"
        assert counts["person"] >= 1 and counts["passport_id"] >= 1

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_electronic_document_response.xml"), baked_ruleset, pii_keyring)
        assert b"5449697775879" in redacted and b"WPSPUK" in redacted


class TestGetTicketingDocument:
    """GetTicketingDocumentRS: passenger name (DC namespace under alternating prefixes)."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("get_ticketing_document_response.xml"))) == "GetTicketingDocumentRS"

    def test_name_encrypt(self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
        redacted, counts = _redact(_fixture("get_ticketing_document_response.xml"), baked_ruleset, pii_keyring)
        assert b"BARNES" not in redacted
        (last,) = xml_texts(redacted, "LastName")
        assert TOKEN_RE.fullmatch(last) and decrypt(last, pii_keyring) == "BARNES"
        assert counts["person"] >= 1

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_ticketing_document_response.xml"), baked_ruleset, pii_keyring)
        assert b"9963865370900" in redacted and b"ICMEVA" in redacted


class TestTravelItineraryHistory:
    """TravelItineraryHistoryRS: PII lives in free-text history lines (extract patterns)."""

    def test_operation(self) -> None:
        op = parse_operation(parse_bytes(_fixture("travel_itinerary_history_response.xml")))
        assert op == "TravelItineraryHistoryRS"

    def test_free_text_pii_redacted_and_name_round_trips(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("travel_itinerary_history_response.xml"), baked_ruleset, pii_keyring)
        assert b"FRIEDMAN" not in redacted and b"YARDEN" not in redacted
        assert counts["person"] >= 2 and counts["email"] >= 1
        assert b"ENC_" in redacted
        # The extracted name span round-trips when replayed upstream.
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"FRIEDMAN" in restored

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("travel_itinerary_history_response.xml"), baked_ruleset, pii_keyring)
        assert b"KSML" in redacted  # meal SSR is operational, not PII


class TestTripSearchPastDatePnr:
    """Trip_SearchRS: past-date PNR with an embedded reservation + extensive history mirrors."""

    def test_operation(self) -> None:
        op = parse_operation(parse_bytes(_fixture("trip_search_past_date_pnr_response.xml")))
        assert op == "Trip_SearchRS"

    def test_names_and_contacts_redacted_and_round_trip(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, counts = _redact(_fixture("trip_search_past_date_pnr_response.xml"), baked_ruleset, pii_keyring)
        for gone in (b"KOVAC", b"MIRELA", b"TSTUSER//MAIL.COM"):
            assert gone not in redacted
        assert counts["person"] >= 2 and counts["phone"] >= 1 and counts["email"] >= 1
        last_names = [t for t in xml_texts(redacted, "LastName") if t.strip()]
        assert last_names and all(TOKEN_RE.fullmatch(n) for n in last_names)
        assert "KOVAC" in {decrypt(n, pii_keyring) for n in last_names}
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"KOVAC" in restored

    def test_non_pii_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("trip_search_past_date_pnr_response.xml"), baked_ruleset, pii_keyring)
        assert b"EKQYAD" in redacted and b"0457976982139" in redacted


class TestQueueAccessUncovered:
    """QueueAccessRS carries only locators/agent-sines (not PII): no rules, forwarded unchanged."""

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture("queue_access_response.xml"))) == "QueueAccessRS"

    def test_uncovered_passes_through(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        outcome = redact_response(
            _fixture("queue_access_response.xml"), channel="sabre", ruleset=baked_ruleset, keyring=pii_keyring
        )
        assert outcome.covered is False
        assert outcome.counts == {}
        assert b"VHTHEO" in outcome.body  # record locators are operational, preserved verbatim


class TestRequiredAnchorFailsClosed:
    """A PII-heavy operation whose required anchor matches nothing fails closed (schema drift guard)."""

    def test_missing_refund_last_name_raises(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # RefundRS with a Traveler that has no lastName attribute: the required anchor matches nothing.
        body = (
            b'<RefundRS xmlns="http://www.sabre.com/ns/Ticketing/ExchangeRefund/1.0">'
            b'<Traveler firstName="ROBERT"/></RefundRS>'
        )
        with pytest.raises(RedactionError):
            _redact(body, baked_ruleset, pii_keyring)


def test_ruleset_version_covers_sabre(baked_ruleset: RuleSet) -> None:
    assert any(rule.channel == "sabre" for rule in baked_ruleset.rules)
    assert "sabre" in baked_ruleset.rules_version
