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

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import (
    deanonymize_request_body,
    parse_operation,
    redact_response,
    redact_response_body,
)
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

SABRE_FIXTURES = FIXTURES_DIR / "sabre"
_MASKED_RE = re.compile(r"^REDACTED$")


def _fixture(name: str) -> bytes:
    return (SABRE_FIXTURES / name).read_bytes()


def _redact(body: bytes, ruleset: RuleSet, keyring: Keyring) -> tuple[bytes, dict[str, int]]:
    return redact_response_body(body, channel="sabre", ruleset=ruleset, keyring=keyring)


def _attrs(body: bytes, attr_name: str) -> list[str]:
    root = parse_bytes(body)
    result = root.xpath(f"//@*[local-name()='{attr_name}']")
    assert isinstance(result, list)
    return [str(value) for value in result]


def _address_line_texts(body: bytes) -> list[str]:
    root = parse_bytes(body)
    nodes = root.xpath("//*[local-name()='AddressLine']/*[local-name()='Text']")
    assert isinstance(nodes, list)
    return [node.text or "" for node in nodes]


# Sabre mirrors passenger data in a parallel history namespace whose date fields use a different
# format, so document assertions have to be namespace-aware rather than by local-name.
S19 = "http://webservices.sabre.com/pnrbuilder/v1_19"
O14 = "http://services.sabre.com/res/or/v1_14"


def _ns_texts(body: bytes, path: str) -> list[str]:
    root = parse_bytes(body)
    nodes = root.xpath(path, namespaces={"s19": S19, "o14": O14})
    assert isinstance(nodes, list)
    return [node.text or "" for node in nodes]


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

    def test_ssn_in_remark_masked_one_way(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("get_reservation_response.xml"), baked_ruleset, pii_keyring)
        assert b"123-45-6789" not in redacted
        assert counts["ssn"] >= 1
        assert b"PSGR SSN" in redacted and b"ON FILE" in redacted  # surrounding text preserved

    def test_meal_ssr_type_encrypted_and_round_trip(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # Meal preference (a GDPR special-category dietary/religion signal) lives in a coded remark
        # and is mirrored in the history/association elements. The type is encrypted in every copy;
        # the operational prefix survives so the line stays recognisable.
        redacted, counts = _redact(_fixture("get_reservation_response.xml"), baked_ruleset, pii_keyring)
        for gone in (b"MOML", b"HALAL"):
            assert gone not in redacted
        for kept in (b"SPL MEAL-", b"MEAL RMKS-", b"A!SPL MEAL-"):
            assert kept in redacted
        # 5 meal copies (MOML remark + 3 mirrors, HALAL remark) + 2 wheelchair free-text nodes.
        assert counts["special_service"] == 7
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"SPL MEAL-MOML" in restored and b"MEAL RMKS-HALAL" in restored
        assert b"A!SPL MEAL-MOML" in restored

    def test_wheelchair_ssr_free_text_encrypted_and_round_trip(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring
    ) -> None:
        redacted, _ = _redact(_fixture("get_reservation_response.xml"), baked_ruleset, pii_keyring)
        # Free text carrying the request is encrypted; the structured <Code> is left intact so the
        # anonymised body still validates against the supplier schema.
        assert b"WCHR REQUESTED FULL LEG" not in redacted
        assert b"<stl19:Code>WCHR</stl19:Code>" in redacted
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"WCHR REQUESTED FULL LEG" in restored

    def test_address_replaced_with_redacted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("get_reservation_response.xml"), baked_ruleset, pii_keyring)
        for gone in (b"1 TEST ST STE 100", b"TEST CITY MN 00000"):
            assert gone not in redacted
        assert counts["address"] == 3
        # Fixed literal (not a variable-length ``*`` mask) to avoid client schema-validation issues.
        address_lines = _address_line_texts(redacted)
        assert address_lines and all(text == "REDACTED" for text in address_lines)

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
            b"2033-04-04",
            b"04APR2033",
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
        # DateOfBirth is a typed field: one-way replaced with a schema-valid sentinel (never a ``*``
        # mask that would crash the caller's date parser) in the format its own namespace uses.
        assert _ns_texts(redacted, "//s19:DOCSEntry/s19:DateOfBirth") == ["1900-01-01"]
        assert _ns_texts(redacted, "//o14:TravelDocument/o14:DateOfBirth") == ["01JAN1900"]
        assert counts["visa"] >= 3  # DOCO entry + or114 DOCO/DOCS free-text lines
        # Address lines are replaced with a fixed ``REDACTED`` literal, not a ``*`` mask.
        address_lines = _address_line_texts(redacted)
        assert address_lines and all(text == "REDACTED" for text in address_lines)

    def test_travel_document_number_masked_in_every_location(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring
    ) -> None:
        # The passport number is carried by the structured DOCS entry, by the or114 history
        # mirror, AND by the supplementary-information block. Covering only one of the three
        # leaves the number in the clear (the CERT defect on PNR TORIWF).
        redacted, _ = _redact(_fixture("get_reservation_pq_history_response.xml"), baked_ruleset, pii_keyring)
        assert b"TT00TEST0" not in redacted
        for path in (
            "//s19:DOCSEntry/s19:DocumentNumber",
            "//o14:TravelDocument/o14:DocumentNumber",
            "//o14:OtherSupplementaryInformation/o14:DocumentNumber",
        ):
            values = _ns_texts(redacted, path)
            assert values and all(_MASKED_RE.fullmatch(v) for v in values), path

    def test_document_expiry_replaced_per_namespace_format(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # Expiry is a typed date the caller parses, so it is replaced with a sentinel rather than
        # masked — in the format its own namespace emits (ISO for s19, DDMMMYYYY for the mirror).
        redacted, _ = _redact(_fixture("get_reservation_pq_history_response.xml"), baked_ruleset, pii_keyring)
        assert b"2033-04-04" not in redacted and b"04APR2033" not in redacted
        assert _ns_texts(redacted, "//s19:DOCSEntry/s19:DocumentExpirationDate") == ["2099-12-31"]
        assert _ns_texts(redacted, "//o14:TravelDocument/o14:DocumentExpirationDate") == ["31DEC2099"]

    def test_document_nationality_replaced_with_valid_code(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # Country of issue and nationality identify the passenger; they are replaced with the
        # ISO 3166-1 user-assigned code so the anonymised body still validates upstream.
        redacted, counts = _redact(_fixture("get_reservation_pq_history_response.xml"), baked_ruleset, pii_keyring)
        for path in (
            "//s19:DOCSEntry/s19:CountryOfIssue",
            "//s19:DOCSEntry/s19:DocumentNationalityCountry",
            "//o14:TravelDocument/o14:DocumentIssueCountry",
            "//o14:TravelDocument/o14:DocumentNationalityCountry",
        ):
            assert _ns_texts(redacted, path) == ["ZZ"], path
        assert counts["nationality"] == 4

    def test_document_kind_and_flags_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # The document kind describes the document, not the passenger, and operational flags are
        # not PII (§7) — redacting them would break APIS consumers for no privacy gain.
        redacted, _ = _redact(_fixture("get_reservation_pq_history_response.xml"), baked_ruleset, pii_keyring)
        assert _ns_texts(redacted, "//s19:DOCSEntry/s19:DocumentType") == ["PP"]
        assert _ns_texts(redacted, "//o14:TravelDocument/o14:Type") == ["DB"]
        for kept in (b"<stl19:ActionCode>HK</stl19:ActionCode>", b"<stl19:NumberInParty>1</stl19:NumberInParty>"):
            assert kept in redacted

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
        # Meal-type redaction is currently scoped to GetReservationRS (and Amadeus PNR_Reply); the
        # TravelItineraryRead history operation has no special-service rule yet, so KSML survives here.
        assert b"KSML" in redacted


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

    def test_ssn_in_remark_masked_one_way(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture("trip_search_past_date_pnr_response.xml"), baked_ruleset, pii_keyring)
        assert b"123-45-6789" not in redacted
        assert counts["ssn"] >= 1


class TestTripSearchPassportDocuments:
    """Trip_SearchRS embeds a whole ``stl19:GetReservationRS``, so its APIS block is the same shape
    the ``sabre.res.docs_*`` rules cover. A thinner ``sabre.trip.docs_*`` copy left the passport
    number, expiry, and nationality in the clear on this operation while the same PNR came back
    fully redacted through GetReservationRS (the CERT split on PNR TORIWF)."""

    FIXTURE = "trip_search_docs_passport_response.xml"

    def test_operation(self) -> None:
        assert parse_operation(parse_bytes(_fixture(self.FIXTURE))) == "Trip_SearchRS"

    def test_passport_number_masked_in_every_location(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture(self.FIXTURE), baked_ruleset, pii_keyring)
        assert b"TT00TEST1" not in redacted
        for path in (
            "//s19:DOCSEntry/s19:DocumentNumber",
            "//o14:TravelDocument/o14:DocumentNumber",
            "//o14:OtherSupplementaryInformation/o14:DocumentNumber",
        ):
            values = _ns_texts(redacted, path)
            assert values and all(_MASKED_RE.fullmatch(v) for v in values), path

    def test_expiry_replaced_per_namespace_format(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture(self.FIXTURE), baked_ruleset, pii_keyring)
        assert _ns_texts(redacted, "//s19:DOCSEntry/s19:DocumentExpirationDate") == ["2099-12-31"]
        assert _ns_texts(redacted, "//o14:TravelDocument/o14:DocumentExpirationDate") == ["31DEC2099"]

    def test_nationality_replaced_with_valid_code(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(_fixture(self.FIXTURE), baked_ruleset, pii_keyring)
        for path in (
            "//s19:DOCSEntry/s19:CountryOfIssue",
            "//s19:DOCSEntry/s19:DocumentNationalityCountry",
            "//o14:TravelDocument/o14:DocumentIssueCountry",
            "//o14:TravelDocument/o14:DocumentNationalityCountry",
        ):
            assert _ns_texts(redacted, path) == ["ZZ"], path
        assert counts["nationality"] == 4

    def test_dob_replaced_with_synthetic_sentinel(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # 1900-01-01 rather than a plausible human date: CERT read the old 1901-01-01 sentinel as
        # live unredacted data. The history mirror keeps its native DDMMMYYYY format.
        redacted, _ = _redact(_fixture(self.FIXTURE), baked_ruleset, pii_keyring)
        assert b"1988-03-14" not in redacted and b"14MAR1988" not in redacted
        assert _ns_texts(redacted, "//s19:DOCSEntry/s19:DateOfBirth") == ["1900-01-01"]
        assert _ns_texts(redacted, "//o14:TravelDocument/o14:DateOfBirth") == ["01JAN1900"]

    def test_gender_always_replaced_with_male(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        # The fixture is female, so an unrewritten node is visible here — a rule that never fired
        # would leave "F" behind rather than blending into the sentinel.
        redacted, _ = _redact(_fixture(self.FIXTURE), baked_ruleset, pii_keyring)
        assert _ns_texts(redacted, "//s19:DOCSEntry/s19:Gender") == ["M"]
        assert _ns_texts(redacted, "//o14:TravelDocument/o14:Gender") == ["M"]

    def test_document_names_and_free_text_redacted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture(self.FIXTURE), baked_ruleset, pii_keyring)
        # The DOCS/DOCO lines mirror the whole document in free text; the history mirror repeats
        # the names. Both survive if only the stl19 structured entry is covered.
        assert b"TESTER" not in redacted and b"ANNA" not in redacted
        for path in ("//o14:TravelDocument/o14:LastName", "//o14:TravelDocument/o14:FirstName"):
            values = _ns_texts(redacted, path)
            assert values and all(_MASKED_RE.fullmatch(v) for v in values), path

    def test_operational_data_preserved(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture(self.FIXTURE), baked_ruleset, pii_keyring)
        assert _ns_texts(redacted, "//s19:DOCSEntry/s19:DocumentType") == ["PP"]
        assert _ns_texts(redacted, "//o14:TravelDocument/o14:Type") == ["PP"]
        assert b"TSTDOC" in redacted  # record locator is operational
        assert b"<stl19:ActionCode>HK</stl19:ActionCode>" in redacted


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


class TestGetReservationHistoryAndContacts:
    """Leak surfaces found in live GetReservationRS traffic: passenger names echoed in
    payment blocks, history association elements, and accounting lines; contact email in
    ``or114:PassengerContactEmail``; Sabre's ``¤``-obfuscated emails in remark lines; and
    phone numbers inside CTC* special requests."""

    def test_operation(self) -> None:
        assert (
            parse_operation(parse_bytes(_fixture("get_reservation_history_contacts_response.xml")))
            == "GetReservationRS"
        )

    def test_payment_and_history_names_encrypted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_reservation_history_contacts_response.xml"), baked_ruleset, pii_keyring)
        # Payment-block PassengerName, history Passengers/Name, history Content, the
        # accounting line, and the or114 comment must not carry the passenger's name.
        assert b"CARTER JAMES" not in redacted
        assert b"CARTER/JAMES" not in redacted
        assert b"ALL/CARTER" not in redacted  # accounting-line name (boundary '/')
        assert b"CONTACT CARTER" not in redacted  # or114 comment (boundary ' ')
        # Non-PII operational text around the scrubbed spans survives.
        assert b"A 000SFC/TRF/0.00/21.00/0.00/ALL/" in redacted
        assert b"<stl19:HistoryAction>ANA</stl19:HistoryAction>" in redacted

    def test_contact_email_and_obfuscated_email_encrypted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(
            _fixture("get_reservation_history_contacts_response.xml"), baked_ruleset, pii_keyring
        )
        # Structured contact email element.
        assert b"JAMES.CARTER@EXAMPLECORP.COM" not in redacted
        # Sabre's remark-encoded email uses ``¤`` instead of ``@`` — a fixed-literal
        # reference match on the collected address can never hit it.
        assert "CLIQUSER-1234567¤EXAMPLECORP.COM".encode() not in redacted
        # History remark association carries the plain-@ variant.
        assert b".CLIQUSER-1234567@EXAMPLECORP.COM" not in redacted
        assert counts["email"] >= 3

    def test_ctc_special_request_phone_encrypted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, counts = _redact(
            _fixture("get_reservation_history_contacts_response.xml"), baked_ruleset, pii_keyring
        )
        # CTCM SSR free text, the agency fare remark, and ReceivedFrom all carry the number.
        assert b"6125550100" not in redacted
        assert counts["phone"] >= 3
        # SSR structure (code, action code) survives; the ReceivedFrom tool prefix stays.
        assert b"<stl19:Code>CTCM</stl19:Code>" in redacted
        assert b"<stl19:ActionCode>HK</stl19:ActionCode>" in redacted
        assert b"MYCWT/AA/" in redacted

    def test_traveller_id_in_remark_encrypted(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_reservation_history_contacts_response.xml"), baked_ruleset, pii_keyring)
        # Corporate booking-tool traveller ids are personal identifiers; the id digits are
        # encrypted in place while the "OBT-GTC/ID-" marker survives.
        assert b"7654321" not in redacted
        assert b"OBT-GTC/ID-" in redacted

    def test_word_boundary_bounds_name_redaction(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        """Names in remark free text are matched on word boundaries (per the referential-
        redaction spec default). A name glued into an alphanumeric agency code with no
        boundary (``*13-JCARTERJA``) is intentionally NOT scrubbed: substring matching there
        would abut a token against trailing text and is a documented limitation, not a
        regression. The bounded occurrences elsewhere are still covered."""
        redacted, _ = _redact(_fixture("get_reservation_history_contacts_response.xml"), baked_ruleset, pii_keyring)
        # Bounded name occurrences (payment block, history, accounting line) are gone.
        assert b"CARTER JAMES" not in redacted
        assert b"CARTER/JAMES" not in redacted
        assert b"ALL/CARTER" not in redacted

    def test_round_trip(self, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
        redacted, _ = _redact(_fixture("get_reservation_history_contacts_response.xml"), baked_ruleset, pii_keyring)
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"CARTER JAMES" in restored
        assert b"CARTER/JAMES" in restored
        assert b"JAMES.CARTER@EXAMPLECORP.COM" in restored
        assert b"6125550100" in restored

    def test_history_phone_node_masked_whole_no_token_abutment(
        self, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        """A history phone element carries a value with a trailing "-W" suffix
        ("MSP1-6125550100-W"). Extracting only the digit span would leave a token abutting the
        "-W", and the greedy token scan on the way back upstream would re-consume it into a
        corrupt token. Phones are masked one-way, and the whole node is masked as a unit — so
        the number is gone, no ENC_ token is produced there, and the rest of the document still
        de-anonymizes cleanly (no corruption)."""
        body = _fixture("get_reservation_history_contacts_response.xml")
        redacted, _ = _redact(body, baked_ruleset, pii_keyring)
        assert b"6125550100" not in redacted
        assert b"MSP1-6125550100-W" not in redacted
        # The whole node is a single REDACTED sentinel (no ENC_ token to abut "-W").
        assert any(_MASKED_RE.fullmatch(text) for text in xml_texts(redacted, "HistoryAssociationElement"))
        # The document still round-trips: every remaining ENC_ token decrypts cleanly.
        deanonymize_request_body(redacted, keyring=pii_keyring)


def test_ruleset_version_covers_sabre(baked_ruleset: RuleSet) -> None:
    assert any(rule.channel == "sabre" for rule in baked_ruleset.rules)
    assert "sabre" in baked_ruleset.rules_version
