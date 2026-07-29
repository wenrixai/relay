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
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

SABRE_FIXTURES = FIXTURES_DIR / "sabre"
# Fixture carrying DOCS DateOfBirth/Gender (both s19 and o14 forms) and PaymentCard expiry.
_TYPED_FIXTURE = "get_reservation_pq_history_response.xml"
_VALID_GENDER_CODES = {"M", "F", "U", "X"}
# The two namespaces express document dates differently, so the contract is per-namespace: a
# sentinel in the other namespace's format is just as unparseable to the caller as a ``*`` mask.
_NS = {
    "s19": "http://webservices.sabre.com/pnrbuilder/v1_19",
    "o14": "http://services.sabre.com/res/or/v1_14",
}
_DDMMMYYYY = "%d%b%Y"


def _redact(body: bytes, ruleset: RuleSet, keyring: Keyring) -> bytes:
    redacted, _ = redact_response_body(body, channel="sabre", ruleset=ruleset, keyring=keyring)
    return redacted


def _ns_texts(body: bytes, path: str) -> list[str]:
    root = parse_bytes(body)
    nodes = root.xpath(path, namespaces=_NS)
    assert isinstance(nodes, list)
    return [node.text or "" for node in nodes]


def test_structured_document_dates_parse_as_iso(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted = _redact((SABRE_FIXTURES / _TYPED_FIXTURE).read_bytes(), baked_ruleset, pii_keyring)
    dates = [
        *_ns_texts(redacted, "//s19:DOCSEntry/s19:DateOfBirth"),
        *_ns_texts(redacted, "//s19:DOCSEntry/s19:DocumentExpirationDate"),
    ]
    assert dates, "fixture must carry s19 document dates to exercise the rules"
    for value in dates:
        # Same contract the caller relies on: the value must be a real ISO date, not a mask.
        datetime.date.fromisoformat(value)


def test_history_document_dates_keep_ddmmmyyyy(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted = _redact((SABRE_FIXTURES / _TYPED_FIXTURE).read_bytes(), baked_ruleset, pii_keyring)
    dates = [
        *_ns_texts(redacted, "//o14:TravelDocument/o14:DateOfBirth"),
        *_ns_texts(redacted, "//o14:TravelDocument/o14:DocumentExpirationDate"),
    ]
    assert dates, "fixture must carry or114 document dates to exercise the rules"
    for value in dates:
        # The history mirror never emits ISO, so an ISO sentinel here is a defect even though the
        # real date is gone: it breaks the caller's parser and reads as unredacted live data.
        datetime.datetime.strptime(value, _DDMMMYYYY).replace(tzinfo=datetime.UTC)


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
