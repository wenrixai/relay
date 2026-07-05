"""Golden redaction test for the baked Amadeus PNR_Reply baseline rules (rules_fallback.json).

Drives the shipped baked ruleset against a sanitized real ``PNR_Retrieve`` reply: names and
the structured frequent-flyer number are encrypted (reversible ``ENC_`` tokens); contact,
passport, and free-text frequent-flyer fields are masked (one-way). Non-PII (PNR reference,
e-ticket/fare freetext) is left untouched, and the encrypted fields round-trip back.
"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path

import pybase64
import pytest

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import deanonymize_request_body, parse_operation, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes

FIXTURE = Path(__file__).parent.parent / "fixtures" / "amadeus" / "pnr_retrieve_response.xml"
_MASKED_RE = re.compile(r"^\*+$")


@pytest.fixture(name="keyring")
def keyring_fixture() -> Keyring:
    key = pybase64.b64encode(bytes([7]) * 32).decode()
    return Keyring.from_json(json.dumps({"0": key}))


@pytest.fixture(name="ruleset")
def ruleset_fixture() -> RuleSet:
    """The baked baseline bundle actually shipped in the image."""
    baked = files("channel_relay.pii").joinpath("rules_fallback.json").read_text()
    return RuleSet.model_validate_json(baked)


@pytest.fixture(name="response_body")
def response_body_fixture() -> bytes:
    return FIXTURE.read_bytes()


def _texts(body: bytes, local_name: str) -> list[str]:
    root = parse_bytes(body)
    return [node.text or "" for node in root.xpath(f"//*[local-name()='{local_name}']")]


def test_operation_is_pnr_reply(response_body: bytes) -> None:
    assert parse_operation(parse_bytes(response_body)) == "PNR_Reply"


def test_counts_match_baseline(response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
    _, counts = redact_response_body(response_body, channel="amadeus", ruleset=ruleset, keyring=keyring)
    assert counts == {"person": 5, "frequent_flyer": 3, "phone": 2, "email": 2, "passport_id": 1}


def test_names_and_ff_number_encrypt_and_round_trip(response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=ruleset, keyring=keyring)
    # Structured name + frequent-flyer nodes are reversible ENC_ tokens.
    surnames = _texts(redacted, "surname")
    first = _texts(redacted, "firstName")[0]
    given = _texts(redacted, "givenName")[0]
    memberships = _texts(redacted, "membershipNumber")
    for token in [*surnames, first, given, *memberships]:
        assert TOKEN_RE.fullmatch(token)
    assert decrypt(surnames[0], keyring) == "PARK"
    assert decrypt(first, keyring) == "JANGBIN MR"
    assert decrypt(given, keyring) == "JANGBIN MR"
    assert all(decrypt(m, keyring) == "4144402077" for m in memberships)
    # Round-trip: re-sending the encrypted body de-anonymizes every token (4 names + 2 FF).
    restored, decrypted = deanonymize_request_body(redacted, keyring=keyring)
    assert decrypted == 6
    assert b"PARK" in restored and b"JANGBIN MR" in restored and b"4144402077" in restored


def test_contact_passport_masked_one_way(response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=ruleset, keyring=keyring)
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
    for node in _texts(redacted, "freeText"):
        assert not node.startswith("ENC_")
    ssr_texts = [t for t in _texts(redacted, "freeText") if _MASKED_RE.fullmatch(t)]
    assert len(ssr_texts) == 6  # 2 CTCE + CTCM + DOCS + FQTS + RESTRICTED


def test_non_pii_preserved(response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=ruleset, keyring=keyring)
    # PNR reference and e-ticket/fare freetext are not PII (§7) and stay verbatim.
    assert b"<controlNumber>DFMJER</controlNumber>" in redacted
    assert b"PAX 205-9297871591/ETNH" in redacted
    assert b"PAX 0000000000 TTP/ET OK ETICKET" in redacted
