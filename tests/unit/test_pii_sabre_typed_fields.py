"""Contract tests: typed Sabre fields stay schema-valid after redaction.

The Wenrix caller parses ``DateOfBirth`` as an ISO date (``ciso8601`` with no error
handling), ``Gender`` as an enum code, and card expiry as a numeric/date-like value. A
``*``-masked value crashes those parsers. These tests lock the invariant that redaction of
typed fields emits parseable output — a future rule edit that reintroduces ``encrypt`` or a
``*`` mask on any of these fields fails here instead of silently breaking the caller.

Shared golden fixtures (``pii_keyring``, ``baked_ruleset``, ``xml_texts``) live in
``tests/conftest.py``.
"""

from __future__ import annotations

import datetime

from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import redact_response_body
from channel_relay.pii.rules import RuleSet
from tests.conftest import FIXTURES_DIR, XmlTexts

SABRE_FIXTURES = FIXTURES_DIR / "sabre"
# Fixture carrying DOCS DateOfBirth/Gender (both s19 and o14 forms) and PaymentCard expiry.
_TYPED_FIXTURE = "get_reservation_pq_history_response.xml"
_VALID_GENDER_CODES = {"M", "F", "U", "X"}


def _redact(body: bytes, ruleset: RuleSet, keyring: Keyring) -> bytes:
    redacted, _ = redact_response_body(body, channel="sabre", ruleset=ruleset, keyring=keyring)
    return redacted


def test_date_of_birth_parses_as_iso_date(baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
    redacted = _redact((SABRE_FIXTURES / _TYPED_FIXTURE).read_bytes(), baked_ruleset, pii_keyring)
    dobs = [t for t in xml_texts(redacted, "DateOfBirth") if t.strip()]
    assert dobs, "fixture must carry DateOfBirth values to exercise the rule"
    for dob in dobs:
        # Same contract the caller relies on: the value must be a real ISO date, not a mask.
        datetime.date.fromisoformat(dob)


def test_gender_stays_a_valid_code(baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
    redacted = _redact((SABRE_FIXTURES / _TYPED_FIXTURE).read_bytes(), baked_ruleset, pii_keyring)
    genders = [t for t in xml_texts(redacted, "Gender") if t.strip()]
    assert genders, "fixture must carry Gender values to exercise the rule"
    for gender in genders:
        assert gender in _VALID_GENDER_CODES, gender


def test_card_expiry_stays_numeric(baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
    redacted = _redact((SABRE_FIXTURES / _TYPED_FIXTURE).read_bytes(), baked_ruleset, pii_keyring)
    expiries = [t for local in ("ExpiryMonth", "ExpiryYear") for t in xml_texts(redacted, local) if t.strip()]
    assert expiries, "fixture must carry card expiry values to exercise the rule"
    for value in expiries:
        # No mask asterisks: the caller reads expiry as a number, so digits must survive.
        assert "*" not in value, value
        assert value.isdigit(), value
