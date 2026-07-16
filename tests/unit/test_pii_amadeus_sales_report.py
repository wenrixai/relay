"""Golden redaction test for the baked Amadeus sales-report baseline rule (rules_fallback.json).

Drives the shipped baked ruleset against a sanitized real ``SalesReports_DisplayQueryReportReply``
response: passenger surnames are encrypted (reversible ``ENC_`` tokens); everything else (order
IDs, document numbers, monetary amounts, booking references) is not PII and is left untouched.

Shared golden fixtures (``pii_keyring``, ``baked_ruleset``, ``xml_texts``) live in the top-level
``tests/conftest.py`` and are reused by the per-channel golden suites.
"""

from __future__ import annotations

import pytest

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import RedactionError, deanonymize_request_body, parse_operation, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

FIXTURE = FIXTURES_DIR / "amadeus" / "sales_report_response.xml"


@pytest.fixture(name="response_body")
def response_body_fixture() -> bytes:
    return FIXTURE.read_bytes()


def test_operation_is_sales_report_reply(response_body: bytes) -> None:
    assert parse_operation(parse_bytes(response_body)) == "SalesReports_DisplayQueryReportReply"


def test_counts_match_baseline(response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    _, counts = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    assert counts == {"person": 2}


def test_names_encrypt_and_round_trip(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts
) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    surnames = xml_texts(redacted, "surname")
    assert len(surnames) == 2
    for token in surnames:
        assert TOKEN_RE.fullmatch(token)
    assert decrypt(surnames[0], pii_keyring) == "PARK JANGBIN MR"
    assert decrypt(surnames[1], pii_keyring) == "JOHNSON MARY MS"
    restored, decrypted = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert decrypted == 2
    assert b"PARK JANGBIN MR" in restored and b"JOHNSON MARY MS" in restored


def test_non_pii_preserved(response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, _ = redact_response_body(response_body, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
    assert b"<id>MH_F96GT9</id>" in redacted
    assert b"<controlNumber>YVARK9</controlNumber>" in redacted
    assert b"<controlNumber>ZQ3L64</controlNumber>" in redacted
    assert b"<number>2322482953027</number>" in redacted
    assert b"<amount>-143.81</amount>" in redacted


def test_required_passenger_name_anchor_fails_closed_on_schema_drift(
    response_body: bytes, baked_ruleset: RuleSet, pii_keyring: Keyring
) -> None:
    drifted = response_body.replace(b"<surname>", b"<surnameV2>").replace(b"</surname>", b"</surnameV2>")
    with pytest.raises(RedactionError):
        redact_response_body(drifted, channel="amadeus", ruleset=baked_ruleset, keyring=pii_keyring)
