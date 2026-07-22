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
_MASKED_RE = re.compile(r"^\*+$")


@pytest.fixture(name="response_body")
def response_body_fixture() -> bytes:
    return FIXTURE.read_bytes()


def test_operation_is_pnr_reply(response_body: bytes) -> None:
    assert parse_operation(parse_bytes(response_body)) == "PNR_Reply"


def test_counts_match_baseline(response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    _, counts = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    assert counts == {"person": 7, "frequent_flyer": 3, "phone": 2, "email": 4, "passport_id": 1, "ssn": 1}


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
    # Given-name fields keep the non-PII honorific in place; only the name is a token, so
    # the bare given name lands in the reference bucket and matches remark free text.
    first_token, first_title = first.split(" ")
    given_token, given_title = given.split(" ")
    assert first_title == given_title == "MR"
    assert TOKEN_RE.fullmatch(first_token) and TOKEN_RE.fullmatch(given_token)
    assert decrypt(surnames[0], pii_keyring) == "PARK"
    assert decrypt(first_token, pii_keyring) == "JANGBIN"
    assert decrypt(given_token, pii_keyring) == "JANGBIN"
    assert all(decrypt(m, pii_keyring) == "4144402077" for m in memberships)
    # Round-trip: re-sending the encrypted body de-anonymizes every token (4 names + 2 FF +
    # 2 name occurrences the reference rule scrubbed from a general remark).
    restored, decrypted = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert decrypted == 8
    assert b"PARK" in restored and b"JANGBIN MR" in restored and b"4144402077" in restored


def test_contact_passport_masked_one_way(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    # Every masked plaintext is gone and its node is now all-asterisks (one-way, no ENC_).
    for gone in [
        b"00852-62374313",
        b"SEAFLY314//ICLOUD.COM",
        b"SEAFLY314//LIVE.COM/EN",
        b"8201049063141",
        b"M037B6058",
        b"NH4144402077",
    ]:
        assert gone not in redacted
    # SSR free-text nodes (email/mobile/passport/FF/RESTRICTED) masked, not tokenized.
    for node in xml_texts(redacted, "freeText"):
        assert not node.startswith("ENC_")
    ssr_texts = [t for t in xml_texts(redacted, "freeText") if _MASKED_RE.fullmatch(t)]
    assert len(ssr_texts) == 6  # 2 CTCE + CTCM + DOCS + FQTS + RESTRICTED


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
    # The honorific is not PII and stays behind in the remark.
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


def test_ruleset_version_covers_amadeus(baked_ruleset: RuleSet) -> None:
    assert any(rule.channel == "amadeus" for rule in baked_ruleset.rules)
    assert "amadeus" in baked_ruleset.rules_version
