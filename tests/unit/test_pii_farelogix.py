"""Golden redaction tests for the baked Farelogix NDC baseline rules (rules_fallback.json).

Farelogix wraps every NDC response in a generic ``XXTransactionResponse`` SOAP Body child, so
the body-derived operation is constant and all rules anchor ``^XXTransactionResponse$``; which
inner message it is (OrderViewRS, AirShoppingRS, …) is decided purely by XPath node presence.
The NDC business elements sit in no namespace; the passenger-name echo and SSR free text sit
under ``AugmentationPoint`` in the ``http://ndc.farelogix.com/aug`` default namespace.

Policy under test (decision: *structured + name-echo only*): structured PII is redacted and
passenger names echoed inside SSR/remark free text are reference-encrypted, but the DOB / gender /
document residue left in a DOCS slash-string (and the DOCA address echo) is intentionally NOT
scrubbed — only the names in those nodes are.
"""

from __future__ import annotations

from channel_relay.channels import get_handler
from channel_relay.config.models import ChannelType
from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import deanonymize_request_body, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from tests.conftest import FIXTURES_DIR, XmlTexts

FARELOGIX_FIXTURES = FIXTURES_DIR / "farelogix"


def _fixture(name: str) -> bytes:
    return (FARELOGIX_FIXTURES / name).read_bytes()


def _redact(body: bytes, ruleset: RuleSet, keyring: Keyring) -> tuple[bytes, dict[str, int]]:
    return redact_response_body(
        body,
        channel="farelogix",
        ruleset=ruleset,
        keyring=keyring,
        operation_parser=get_handler(ChannelType.FARELOGIX_AA).parse_operation,
    )


def test_operation_parser_returns_generic_transaction_wrapper() -> None:
    handler = get_handler(ChannelType.FARELOGIX_AA)
    assert handler.parse_operation(parse_bytes(_fixture("order_view_response.xml"))) == "XXTransactionResponse"


def test_order_view_redacts_every_pii_surface(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, counts = _redact(_fixture("order_view_response.xml"), baked_ruleset, pii_keyring)

    assert counts == {
        "person": 9,
        "email": 1,
        "frequent_flyer": 1,
        "gender": 2,
        "dob": 4,
        "passport_id": 1,
        "phone": 1,
        "address": 7,
        "payment": 3,
    }

    # Structured PII plaintext is gone.
    for gone in (
        b"DAVE.DOE@EXAMPLE.COM",
        b"17865554433",
        b"X1234321",
        b"AA9988776",
        b"XXXXXXXXXXXX0007",
        b"124 BILLING STREET",
        b"<Street>123 STREET</Street>",
        b"<CityName>MIAMI</CityName>",
        b"<GivenName>DAVE</GivenName>",
        b"<Surname>DOE</Surname>",
    ):
        assert gone not in redacted


def test_order_view_survivors_are_untouched(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    redacted, _ = _redact(_fixture("order_view_response.xml"), baked_ruleset, pii_keyring)
    # Operational identifiers are not PII and must survive verbatim.
    for survivor in (b"00157549767336", b"BMSHY5", b"SN082H12Q84A5", b">ADT<", b"MIA1S2179", b"07560685"):
        assert survivor in redacted


def test_names_encrypt_and_round_trip(baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
    redacted, _ = _redact(_fixture("order_view_response.xml"), baked_ruleset, pii_keyring)

    surnames = xml_texts(redacted, "Surname")
    given = xml_texts(redacted, "GivenName")
    aug_names = xml_texts(redacted, "Name")
    holder = xml_texts(redacted, "CardHolderName")
    assert surnames and given and holder
    for token in [*surnames, *given, *aug_names, *holder]:
        assert TOKEN_RE.fullmatch(token)
    assert {decrypt(t, pii_keyring) for t in surnames} == {"DOE"}
    assert {decrypt(t, pii_keyring) for t in given} == {"DAVE", "RACHEL"}
    assert {decrypt(t, pii_keyring) for t in aug_names} == {"DAVE MR", "DOE"}
    assert {decrypt(t, pii_keyring) for t in holder} == {"DAVE DOE"}

    # Encrypted names de-anonymize on the way back upstream.
    restored, _ = deanonymize_request_body(redacted, keyring=pii_keyring)
    assert b"DAVE" in restored and b"RACHEL" in restored and b"DOE" in restored


def test_masked_and_replaced_fields(baked_ruleset: RuleSet, pii_keyring: Keyring, xml_texts: XmlTexts) -> None:
    redacted, _ = _redact(_fixture("order_view_response.xml"), baked_ruleset, pii_keyring)
    # dob replaced with a fixed sentinel (kept a valid date so downstream parsers survive).
    assert set(xml_texts(redacted, "Birthdate")) == {"1901-01-01"}
    # gender masked, not encrypted.
    for value in xml_texts(redacted, "Gender"):
        assert set(value) == {"*"}
    # identity document number masked.
    assert all(set(v) == {"*"} for v in xml_texts(redacted, "IdentityDocumentNumber"))


def test_docs_free_text_names_encrypted_dob_and_gender_remain(baked_ruleset: RuleSet, pii_keyring: Keyring) -> None:
    """The DOCS slash-string has its passenger names reference-encrypted; the DOB/gender residue
    stays (the *structured + name-echo only* decision), and the TKNE ticket number is untouched."""
    redacted, _ = _redact(_fixture("order_view_response.xml"), baked_ruleset, pii_keyring)
    text = redacted.decode()
    # Names no longer present in the DOCS free text; DOB + gender token still there.
    assert "//DOE/DAVE" not in text
    assert "/////01MAR77/M//ENC_" in text
    # Ticket number in the TKNE SSR free text is not PII and survives.
    assert "00157549767336C1" in text


def test_farelogix_is_represented_in_rules_version(baked_ruleset: RuleSet) -> None:
    assert "farelogix" in baked_ruleset.rules_version
