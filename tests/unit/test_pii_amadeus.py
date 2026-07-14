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
from channel_relay.pii.engine import RedactionError, deanonymize_request_body, parse_operation, redact_response_body
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
    assert counts == {"person": 5, "frequent_flyer": 3, "phone": 2, "email": 2, "passport_id": 1}


def test_names_and_ff_number_encrypt_and_round_trip(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    # Structured name + frequent-flyer nodes are reversible ENC_ tokens.
    surnames = xml_texts(redacted, "surname")
    first = xml_texts(redacted, "firstName")[0]
    given = xml_texts(redacted, "givenName")[0]
    memberships = xml_texts(redacted, "membershipNumber")
    for token in [*surnames, first, given, *memberships]:
        assert TOKEN_RE.fullmatch(token)
    assert decrypt(surnames[0], pii_keyring) == "PARK"
    assert decrypt(first, pii_keyring) == "JANGBIN MR"
    assert decrypt(given, pii_keyring) == "JANGBIN MR"
    assert all(decrypt(m, pii_keyring) == "4144402077" for m in memberships)
    # Round-trip: re-sending the encrypted body de-anonymizes every token (4 names + 2 FF).
    restored, decrypted = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert decrypted == 6
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


def test_non_pii_preserved(response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    # PNR reference and e-ticket/fare freetext are not PII (§7) and stay verbatim.
    assert b"<controlNumber>DFMJER</controlNumber>" in redacted
    assert b"PAX 205-9297871591/ETNH" in redacted
    assert b"PAX 0000000000 TTP/ET OK ETICKET" in redacted


def test_required_passenger_name_anchor_fails_closed_on_schema_drift(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    drifted = response_body.replace(b"<surname>", b"<surnameV2>").replace(b"</surname>", b"</surnameV2>")
    with pytest.raises(RedactionError):
        redact_response_body(drifted, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
