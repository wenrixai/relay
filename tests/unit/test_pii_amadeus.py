"""Golden redaction test for the baked Amadeus PNR_Reply baseline rules (rules_fallback.json).

Drives the shipped baked ruleset against a sanitized real ``PNR_Retrieve`` reply: names and
the structured frequent-flyer number are encrypted (reversible ``ENC_`` tokens); contact,
passport, and free-text frequent-flyer fields are masked (one-way). Non-PII (PNR reference,
e-ticket/fare freetext) is left untouched, and the encrypted fields round-trip back.

Shared golden fixtures (``pii_keyring``, ``baked_ruleset``, ``xml_texts``) live in the
top-level ``tests/conftest.py`` and are reused by the per-channel golden suites.
"""

from __future__ import annotations

import re

import pytest

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import deanonymize_request_body, parse_operation, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

FIXTURE = FIXTURES_DIR / "amadeus" / "pnr_retrieve_response.xml"
_MASKED_RE = re.compile(r"^REDACTED$")


@pytest.fixture(name="response_body")
def response_body_fixture() -> bytes:
    return FIXTURE.read_bytes()


def test_operation_is_pnr_reply(response_body: bytes) -> None:
    assert parse_operation(parse_bytes(response_body)) == "PNR_Reply"


def test_counts_match_baseline(response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    _, counts = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    assert counts == {
        "person": 7,
        "frequent_flyer": 3,
        "phone": 2,
        "email": 4,
        "passport_id": 1,
        "visa": 1,
        "gender": 2,
        "ssn": 1,
        "special_service": 6,
    }


def test_names_and_ff_number_encrypt_and_round_trip(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    # Structured name + frequent-flyer nodes are reversible ENC_ tokens.
    surnames = xml_texts(redacted, "surname")
    first = xml_texts(redacted, "firstName")[0]
    given = xml_texts(redacted, "givenName")[0]
    memberships = xml_texts(redacted, "membershipNumber")
    for token in [*surnames, *memberships]:
        assert TOKEN_RE.fullmatch(token)
    # Given-name fields hold a name plus an honorific. Each is tokenized independently: the name
    # span stays the value collected into the ``person`` bucket (so the reference pass still finds
    # the bare name in remark free text), while the title is redacted by its own ``gender`` rule.
    first_token, first_title = first.split(" ")
    given_token, given_title = given.split(" ")
    for token in (first_token, first_title, given_token, given_title):
        assert TOKEN_RE.fullmatch(token)
    assert decrypt(surnames[0], pii_keyring) == "PARK"
    assert decrypt(first_token, pii_keyring) == "JANGBIN"
    assert decrypt(given_token, pii_keyring) == "JANGBIN"
    assert decrypt(first_title, pii_keyring) == decrypt(given_title, pii_keyring) == "MR"
    assert all(decrypt(m, pii_keyring) == "4144402077" for m in memberships)
    # Round-trip: re-sending the encrypted body de-anonymizes every token (4 names + 2 honorifics +
    # 2 FF + 2 name occurrences the reference rule scrubbed from a general remark + 2
    # special-service SSR).
    restored, decrypted = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert decrypted == 12
    assert b"PARK" in restored and b"JANGBIN MR" in restored and b"4144402077" in restored


def test_contact_passport_masked_one_way(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    # Every masked plaintext is gone and its node is now the REDACTED sentinel (one-way, no ENC_).
    for gone in [
        b"00852-62374313",
        b"SEAFLY314//ICLOUD.COM",
        b"SEAFLY314//LIVE.COM/EN",
        b"8201049063141",
        b"M037B6058",
        b"189200313",
        b"NH4144402077",
    ]:
        assert gone not in redacted
    # Contact/identity SSR free-text nodes (email/mobile/passport/visa/FF/RESTRICTED) are masked,
    # not tokenized. Meal/wheelchair SSR free text is encrypted instead (see the special-service
    # test), so exactly those two are the only ``ENC_`` free-text nodes.
    free_texts = xml_texts(redacted, "freeText")
    ssr_texts = [t for t in free_texts if _MASKED_RE.fullmatch(t)]
    assert len(ssr_texts) == 7  # 2 CTCE + CTCM + DOCS + DOCO + FQTS + RESTRICTED
    encrypted = [t for t in free_texts if t.startswith("ENC_")]
    assert len(encrypted) == 2  # AVML meal + WCHR wheelchair


def test_doco_visa_free_text_masked_one_way(response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    """DOCO carries visa data (number, place/date of issue, destination). It is masked like the
    DOCS passport line — covering only ``type='DOCS'`` left the visa number in the clear."""
    redacted, counts = redact_response_body(
        response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
    )
    assert b"PHL PH/V/189200313/PH//USA//05JUN29" not in redacted
    assert counts["visa"] == 1
    # The structured type code is left intact so the anonymised PNR still validates upstream.
    assert b"<type>DOCO</type>" in redacted


def test_given_name_honorific_redacted_and_round_trips(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    """A title discloses gender (and marital status for MRS/MISS), so it is redacted rather than
    treated as operational text — reversing the earlier honorific-preserving stance."""
    redacted, counts = redact_response_body(
        response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
    )
    assert counts["gender"] == 2  # firstName + givenName
    # Nothing but tokens is left in either given-name field: name and title are separate spans,
    # so no plaintext fragment survives. (A substring check would be unsound here — base64url
    # token payloads can contain the letters of a title.)
    for local in ("firstName", "givenName"):
        for value in xml_texts(redacted, local):
            assert value.split(" ") and all(TOKEN_RE.fullmatch(part) for part in value.split(" ")), (local, value)
    # It is encrypted, not dropped, so the upstream channel still receives the real title.
    restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert b"<firstName>JANGBIN MR</firstName>" in restored


def test_meal_and_wheelchair_ssr_encrypted_and_round_trip(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    # Meal/wheelchair SSR free text (special-category dietary/health signals) is encrypted and
    # round-trips; the structured <type> code is replaced one-way with the generic OTHS sentinel
    # (see test_bare_meal_and_wheelchair_ssr_type_replaced) so the PNR still validates upstream.
    redacted, counts = redact_response_body(
        response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
    )
    for gone in (b"VEGETARIAN MEAL", b"WHEELCHAIR TO GATE"):
        assert gone not in redacted
    assert counts["special_service"] == 6  # 2 freeText encrypts + 4 <type> sentinels
    restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert b"VEGETARIAN MEAL" in restored and b"WHEELCHAIR TO GATE" in restored


def test_bare_meal_and_wheelchair_ssr_type_replaced(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    """A meal/wheelchair SSR may carry no free text at all — the <type> code itself is then the
    only special-category signal (the CERT WCMP/VOML leak on PNR 87TB9I). The code family is
    matched with an EXSLT ``re:test`` predicate (not a per-code allow-list) and the enum node is
    replaced with the generic ``OTHS`` sentinel: schema-valid, and — unlike a category-preserving
    sentinel — it hides even the fact that a meal or wheelchair was requested."""
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    for gone in (b"<type>AVML</type>", b"<type>WCHR</type>", b"<type>WCMP</type>", b"<type>VOML</type>"):
        assert gone not in redacted
    assert redacted.count(b"<type>OTHS</type>") == 4
    # Non-special-service SSR types keep their codes (DOCO asserted in the visa test too).
    assert b"<type>DOCS</type>" in redacted and b"<type>FQTV</type>" in redacted
    # Operational SSR structure survives.
    assert b"<status>HN</status>" in redacted


def test_ssn_in_general_remark_masked_one_way(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    redacted, counts = redact_response_body(
        response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
    )
    assert b"123-45-6789" not in redacted
    assert counts["ssn"] == 1
    assert b"PSGR SSN" in redacted and b"ON FILE" in redacted  # surrounding remark text preserved


def test_email_in_general_remark_masked_one_way(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    """Email embedded in RM general-remark free text (miscellaneousRemarks + extendedRemark
    mirror) is masked in place; surrounding operational remark text is preserved."""
    redacted, counts = redact_response_body(
        response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
    )
    assert b"AGENT@EXAMPLE.COM" not in redacted
    assert counts["email"] == 4  # 2 CTCE SSR + 2 general-remark freetext mirrors
    # Only the email span is masked; the operational remark text stays verbatim.
    assert b"PROCESSED BY CBR TO" in redacted and b"*10JUL*0948Z" in redacted
    assert b"*0702*" in redacted


def test_name_in_general_remark_encrypted_via_reference(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    """A passenger name echoed in a structuredRemark freetext (e.g. an agent note) is not a
    structured field, but it IS one of the values a structured name field already collected
    this pass — the reference rule scrubs it, preserving the surrounding operational text and
    reusing the same token the structured surname/firstName field received."""
    redacted, counts = redact_response_body(
        response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
    )
    assert b"PARK JANGBIN MR" not in redacted
    assert counts["person"] == 7  # 4 structured name fields + 1 FF freetext mirror + 2 remark hits
    assert b"0112*" in redacted and b"RQ SEAT CHANGE" in redacted  # surrounding remark text preserved

    surnames = xml_texts(redacted, "surname")
    remark_text = next(t for t in xml_texts(redacted, "freetext") if "0112*" in t)
    remark_tokens = [tok for tok in remark_text.replace("0112*", "").split() if TOKEN_RE.fullmatch(tok)]
    assert len(remark_tokens) == 2
    assert remark_tokens[0] == surnames[0]  # reference hit reuses the structured field's token
    assert decrypt(remark_tokens[1], pii_keyring) == "JANGBIN"
    # The honorific rule is anchored to the structured given-name fields, and the title is typed
    # ``gender`` so it never enters the ``person`` reference bucket — a two-letter title searched
    # for across every remark would redact unrelated operational text. It therefore survives here.
    assert " MR RQ SEAT CHANGE" in remark_text


def test_non_pii_preserved(response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    # PNR reference and e-ticket/fare freetext are not PII (§7) and stay verbatim.
    assert b"<controlNumber>DFMJER</controlNumber>" in redacted
    assert b"PAX 205-9297871591/ETNH" in redacted
    assert b"PAX 0000000000 TTP/ET OK ETICKET" in redacted


CONTACT_REMARKS_FIXTURE = FIXTURES_DIR / "amadeus" / "pnr_retrieve_contact_remarks_response.xml"


@pytest.fixture(name="contact_remarks_body")
def contact_remarks_body_fixture() -> bytes:
    return CONTACT_REMARKS_FIXTURE.read_bytes()


class TestContactRemarks:
    """PII that exists ONLY in RM free text (never in a structured field) must still be
    scrubbed: agent-entered name lines, arrival-contact lines, and emergency-contact
    (ECTC) entries carry third-party names and phone numbers the reference pass cannot
    see because no field rule ever collected them."""

    def test_remark_name_lines_encrypted(
        self, contact_remarks_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
    ) -> None:
        redacted, _ = redact_response_body(
            contact_remarks_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        # NAME- line: full name block (including the middle name HUGO that no structured
        # field carries) is gone; the NAME- marker survives.
        assert b"HUGO" not in redacted
        assert b"NAME-" in redacted
        # *ARR* contact line: the SURNAME/GIVEN block is gone; the *ARR* marker survives.
        assert b"JOHNSON/PETER" not in redacted
        assert b"*ARR*" in redacted

    def test_emergency_contact_name_and_phones_encrypted(
        self, contact_remarks_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
    ) -> None:
        redacted, counts = redact_response_body(
            contact_remarks_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        # ECTC third-party contact: name and phone are gone from both the
        # miscellaneousRemarks entry and its structuredRemark mirror.
        assert b"SARAH" not in redacted
        assert b"70001112" not in redacted
        assert b"7000111222" not in redacted
        assert counts["phone"] >= 3  # ECTC TEL x2 mirrors + *ARR* PH number
        # Operational remark structure survives.
        assert b"ECTC/TEL-" in redacted and b"/R-SISTER/C-EG" in redacted

    def test_remark_tokens_round_trip(
        self, contact_remarks_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
    ) -> None:
        redacted, _ = redact_response_body(
            contact_remarks_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"SARAH JOHNSON" in restored
        assert b"PH44-7000111222" in restored
        assert b"NAME-PETER/HUGO/JOHNSON" in restored


THIRD_PARTY_FIXTURE = FIXTURES_DIR / "amadeus" / "pnr_retrieve_third_party_remarks_response.xml"


@pytest.fixture(name="third_party_body")
def third_party_body_fixture() -> bytes:
    return THIRD_PARTY_FIXTURE.read_bytes()


class TestThirdPartyRemarks:
    """A customer-reported gap: PII carried only by RM remark free text, plus the FP and OS
    elements that had no rule at all.

    Every RM remark is emitted twice — once under ``miscellaneousRemarks/remarks`` with the
    leading ``*`` inside the text, once under ``extendedRemark/structuredRemark`` with that ``*``
    hoisted into ``category``. Patterns must therefore not require the ``*``, and each assertion
    below covers both mirrors.
    """

    def test_orderer_name_encrypted_in_both_mirrors(
        self, third_party_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, _ = redact_response_body(
            third_party_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        # The orderer is a third party: no structured name node carries them, so the reference
        # pass cannot see the value and a field rule has to reach it.
        assert b"GREENE" not in redacted
        assert b"ALICE" not in redacted
        # Both markers survive, in both mirrors (2 x ACEORB + 2 x ACECRM-ORDERER).
        assert redacted.count(b"ACEORB-") == 2
        assert redacted.count(b"ACECRM-ORDERER-") == 2
        orderer_texts = [t for t in xml_texts(redacted, "freetext") if "ACEORB-" in t]
        assert len(orderer_texts) == 2
        for text in orderer_texts:
            token = text.split("ACEORB-")[1]
            assert TOKEN_RE.fullmatch(token)
            assert decrypt(token, pii_keyring) == "GREENE ALICE"

    def test_remark_dob_and_gender_use_format_preserving_sentinels(
        self, third_party_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, _ = redact_response_body(
            third_party_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        assert b"02FEB90" not in redacted
        # Identity-document spans in free text keep their shape (a DDMMMYY-shaped sentinel and the
        # existing gender sentinel), so a consumer parsing the remark line still succeeds.
        dob_texts = [t for t in xml_texts(redacted, "freetext") if t.startswith("DOB-")]
        assert dob_texts == ["DOB-01JAN00/GENDER-M", "DOB-01JAN00/GENDER-M"]

    def test_person_linked_identifiers_encrypted(
        self, third_party_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, _ = redact_response_body(
            third_party_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        for gone in (b"37000001", b"15000000001", b"770000001", b"LH100000000001"):
            assert gone not in redacted
        texts = xml_texts(redacted, "freetext")
        employee = next(t for t in texts if t.startswith("*ACECRM-EMPLOYEE ID-"))
        token = employee.removeprefix("*ACECRM-EMPLOYEE ID-")
        assert TOKEN_RE.fullmatch(token)
        assert decrypt(token, pii_keyring) == "37000001"
        # The template remark carries the same marker with no value; it must be untouched,
        # trailing hyphen included.
        assert b"EMPLOYEE ID MANDATORY, RM*ACECRM-EMPLOYEE ID-<" in redacted

    def test_form_of_payment_element_card_redacted(
        self, third_party_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
    ) -> None:
        redacted, _ = redact_response_body(
            third_party_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        # The FP element had no rule at all. Supplier-side masking is not trusted: the surviving
        # digits still reveal the last four.
        assert b"XXXXXXXXXX1111" not in redacted
        assert b"0630" not in redacted
        fp = next(t for t in xml_texts(redacted, "longFreetext") if t.startswith("PAX CCDC"))
        assert fp == "PAX CCDCREDACTED/0000"

    def test_organisation_codes_and_ticket_number_preserved(
        self, third_party_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
    ) -> None:
        redacted, _ = redact_response_body(
            third_party_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        # Organisation-level corporate account codes are commercial data, not personal data:
        # redacting them breaks fare reissue. Ticket number and locator are operational (§7).
        for kept in (
            b"CMP OPK000FI",
            b"OIN FI00000",
            b"NCA TSTCOOP",
            b"PAX 105-2400000001/ETAY/12AUG26/HELMK0000/19000000",
            b"<controlNumber>TQ7XF4</controlNumber>",
        ):
            assert kept in redacted

    def test_third_party_tokens_round_trip(
        self, third_party_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
    ) -> None:
        redacted, _ = redact_response_body(
            third_party_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring
        )
        restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
        assert b"*ACEORB-GREENE ALICE" in restored
        assert b"ACECRM-ORDERER-GREENE ALICE" in restored
        assert b"*ACECRM-EMPLOYEE ID-37000001" in restored
        assert b"CYTRIC PROFILE REF:15000000001" in restored
        assert b"CP/LH100000000001" in restored


def test_ruleset_version_covers_amadeus(baked_ruleset: RuleSet) -> None:
    assert any(rule.channel == "amadeus" for rule in baked_ruleset.rules)
    assert "amadeus" in baked_ruleset.rules_version
