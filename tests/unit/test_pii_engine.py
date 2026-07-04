"""Redaction engine tests: operation parsing, rule application, fail-closed (T2.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pybase64
import pytest

from channel_relay.pii.codec import TOKEN_RE, decrypt, encrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import (
    DeanonymizationError,
    RedactionError,
    deanonymize_request_body,
    parse_operation,
    redact_response_body,
)
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mock"


@pytest.fixture(name="keyring")
def keyring_fixture() -> Keyring:
    key = pybase64.b64encode(bytes([7]) * 32).decode()
    return Keyring.from_json(json.dumps({"0": key}))


@pytest.fixture(name="ruleset")
def ruleset_fixture() -> RuleSet:
    return RuleSet.model_validate_json((FIXTURES / "rules.json").read_text())


@pytest.fixture(name="response_body")
def response_body_fixture() -> bytes:
    return (FIXTURES / "soap_response.xml").read_bytes()


def find_text(body: bytes, local_name: str) -> str | None:
    root = parse_bytes(body)
    nodes = root.xpath(f"//*[local-name()='{local_name}']")
    return nodes[0].text if nodes else None


class TestParseOperation:
    def test_soap_body_first_child(self, response_body: bytes) -> None:
        assert parse_operation(parse_bytes(response_body)) == "PNR_RetrieveResponse"

    def test_plain_root_element(self) -> None:
        assert parse_operation(parse_bytes(b"<PNR_Retrieve><Id>1</Id></PNR_Retrieve>")) == "PNR_Retrieve"

    def test_namespaced_root(self) -> None:
        assert parse_operation(parse_bytes(b'<op:Book xmlns:op="urn:x"/>')) == "Book"


class TestRedaction:
    def test_encrypt_fields_decrypt_back(self, response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
        redacted, counts = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        name = find_text(redacted, "Name")
        email = find_text(redacted, "Email")
        assert name is not None and TOKEN_RE.fullmatch(name)
        assert email is not None and TOKEN_RE.fullmatch(email)
        assert decrypt(name, keyring) == "John Smith"
        assert decrypt(email, keyring) == "john.smith@example.com"
        assert counts["person"] == 1
        assert counts["email"] == 1

    def test_mask_keeps_prefix(self, response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
        redacted, _ = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        assert find_text(redacted, "Card") == "4111" + "*" * 12

    def test_replace_action(self, response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
        redacted, _ = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        assert find_text(redacted, "Address") == "REDACTED"

    def test_remove_action(self, response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
        redacted, _ = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        assert not find_text(redacted, "Passport")

    def test_ignored_pattern_skipped(self, response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
        redacted, _ = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        assert find_text(redacted, "FrequentFlyer") == "TMX12345"

    def test_attribute_redacted(self, response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
        redacted, _ = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        root = parse_bytes(redacted)
        loyalty = root.xpath("//*[local-name()='Traveler']/@loyalty")[0]
        assert TOKEN_RE.fullmatch(loyalty)
        assert decrypt(loyalty, keyring) == "FF-778899"

    def test_unmatched_channel_and_operation_rules_inert(
        self, response_body: bytes, ruleset: RuleSet, keyring: Keyring
    ) -> None:
        redacted, _ = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        assert find_text(redacted, "PnrRef") == "ABC123"  # not PII; other-channel/op rules inert

    def test_unknown_namespace_prefix_is_no_match(
        self, response_body: bytes, ruleset: RuleSet, keyring: Keyring
    ) -> None:
        # Rule mock.pnr.badns.001 uses an undeclared prefix; must not raise.
        _, counts = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        # name + email + card + address + passport + loyalty attr; FrequentFlyer skipped.
        assert sum(counts.values()) == 6

    def test_structure_and_namespaces_preserved(self, response_body: bytes, ruleset: RuleSet, keyring: Keyring) -> None:
        redacted, _ = redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)
        root = parse_bytes(redacted)
        assert root.tag == "{http://schemas.xmlsoap.org/soap/envelope/}Envelope"
        body = root[0]
        assert body[0].tag == "{urn:mock:pnr}PNR_RetrieveResponse"

    def test_failure_raises_redaction_error(
        self, response_body: bytes, ruleset: RuleSet, keyring: Keyring, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*args: object, **kwargs: object) -> str:
            raise ValueError("crypto exploded")

        monkeypatch.setattr("channel_relay.pii.engine.encrypt", boom)
        with pytest.raises(RedactionError):
            redact_response_body(response_body, channel="mock", ruleset=ruleset, keyring=keyring)


NS = "urn:mock:pnr"


def _ref_ruleset(*, name_path: str = "//m:Traveler/m:Name", **ref_overrides: object) -> RuleSet:
    field_rule = {
        "id": "r.person",
        "channel": "mock",
        "operation": "^PNR_Retrieve",
        "path": name_path,
        "namespaces": {"m": NS},
        "pii_type": "person",
        "method": "encrypt",
    }
    reference_rule = {
        "id": "r.remark",
        "rule_type": "reference",
        "channel": "mock",
        "operation": "^PNR_Retrieve",
        "path": "//m:Remark/m:Text",
        "namespaces": {"m": NS},
        "source_pii_types": ["person"],
        "pii_type": "person",
        "method": "encrypt",
        **ref_overrides,
    }
    return RuleSet.model_validate(
        {"schema_version": "1.0", "rules_version": "t", "rules": [field_rule, reference_rule]}
    )


def _doc(name: str, *remarks: str) -> bytes:
    remark_xml = "".join(f"<Remark><Text>{text}</Text></Remark>" for text in remarks)
    return (f'<PNR_Retrieve xmlns="{NS}"><Traveler><Name>{name}</Name></Traveler>{remark_xml}</PNR_Retrieve>').encode()


def _remark_texts(body: bytes) -> list[str]:
    root = parse_bytes(body)
    return [node.text or "" for node in root.xpath("//*[local-name()='Text']")]


def _extract_ruleset(
    *,
    path: str = "//m:Remark/m:Text",
    method: str = "mask",
    required: bool = False,
    pattern: str = r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    **extra: object,
) -> RuleSet:
    rule: dict[str, object] = {
        "id": "r.extract",
        "channel": "mock",
        "operation": "^PNR_Retrieve",
        "path": path,
        "namespaces": {"m": NS},
        "pii_type": "email",
        "method": method,
        "extract_patterns": [{"pattern": pattern}],
        "required": required,
        **extra,
    }
    return RuleSet.model_validate({"schema_version": "1.0", "rules_version": "t", "rules": [rule]})


class TestReferenceRedaction:
    def test_name_scrubbed_from_remark_round_trips(self, keyring: Keyring) -> None:
        body = _doc("John Smith", "PSGR JOHN SMITH RQ WHEELCHAIR")
        redacted, counts = redact_response_body(body, channel="mock", ruleset=_ref_ruleset(), keyring=keyring)
        text = _remark_texts(redacted)[0]
        assert "JOHN SMITH" not in text
        assert text.startswith("PSGR ") and text.endswith(" RQ WHEELCHAIR")
        token = text.removeprefix("PSGR ").removesuffix(" RQ WHEELCHAIR")
        assert TOKEN_RE.fullmatch(token) and decrypt(token, keyring) == "JOHN SMITH"
        assert counts["person"] == 2  # structured Name + one remark occurrence

    def test_search_bounded_to_target_path(self, keyring: Keyring) -> None:
        # A collected value sitting in a non-target node is left alone.
        body = (
            f'<PNR_Retrieve xmlns="{NS}"><Traveler><Name>John Smith</Name></Traveler>'
            "<Other>JOHN SMITH ELSEWHERE</Other></PNR_Retrieve>"
        ).encode()
        redacted, _ = redact_response_body(body, channel="mock", ruleset=_ref_ruleset(), keyring=keyring)
        other = parse_bytes(redacted).xpath("//*[local-name()='Other']")[0].text
        assert other == "JOHN SMITH ELSEWHERE"

    def test_word_boundary_prevents_substring(self, keyring: Keyring) -> None:
        body = _doc("John", "JOHNSON PAID CASH")
        redacted, _ = redact_response_body(body, channel="mock", ruleset=_ref_ruleset(), keyring=keyring)
        assert _remark_texts(redacted)[0] == "JOHNSON PAID CASH"

    def test_short_value_below_min_len_skipped(self, keyring: Keyring) -> None:
        body = _doc("Li", "MR LI PAID")
        redacted, _ = redact_response_body(body, channel="mock", ruleset=_ref_ruleset(), keyring=keyring)
        assert _remark_texts(redacted)[0] == "MR LI PAID"

    def test_case_insensitive_preserves_surrounding(self, keyring: Keyring) -> None:
        body = _doc("John", "john smith here")
        redacted, _ = redact_response_body(body, channel="mock", ruleset=_ref_ruleset(), keyring=keyring)
        text = _remark_texts(redacted)[0]
        assert text.endswith(" smith here")
        token = text.removesuffix(" smith here")
        assert decrypt(token, keyring) == "john"

    def test_empty_source_bucket_is_noop(self, keyring: Keyring) -> None:
        # No structured name present -> nothing collected -> remark untouched.
        body = f'<PNR_Retrieve xmlns="{NS}"><Remark><Text>JOHN SMITH</Text></Remark></PNR_Retrieve>'.encode()
        redacted, _ = redact_response_body(body, channel="mock", ruleset=_ref_ruleset(), keyring=keyring)
        assert _remark_texts(redacted)[0] == "JOHN SMITH"

    def test_reference_encrypt_failure_fails_closed(self, keyring: Keyring, monkeypatch: pytest.MonkeyPatch) -> None:
        body = _doc("John Smith", "PSGR JOHN SMITH")
        calls = {"n": 0}

        def sometimes_boom(value: str, kr: Keyring) -> str:
            calls["n"] += 1
            if calls["n"] > 1:  # let phase-1 field encrypt succeed, blow up in phase 2
                raise ValueError("boom")
            return "ENC_ok"

        monkeypatch.setattr("channel_relay.pii.engine.encrypt", sometimes_boom)
        with pytest.raises(RedactionError):
            redact_response_body(body, channel="mock", ruleset=_ref_ruleset(), keyring=keyring)


class TestExtractPatternRedaction:
    def test_partial_email_mask_preserves_surrounding_text(self, keyring: Keyring) -> None:
        body = _doc("John Smith", "EMAIL john.smith@example.com OK")
        redacted, counts = redact_response_body(body, channel="mock", ruleset=_extract_ruleset(), keyring=keyring)
        assert _remark_texts(redacted)[0] == "EMAIL ********************** OK"
        assert counts["email"] == 1

    def test_partial_email_encrypt_round_trips(self, keyring: Keyring) -> None:
        body = _doc("John Smith", "EMAIL john.smith@example.com OK")
        redacted, counts = redact_response_body(
            body, channel="mock", ruleset=_extract_ruleset(method="encrypt"), keyring=keyring
        )
        text = _remark_texts(redacted)[0]
        assert text.startswith("EMAIL ") and text.endswith(" OK")
        token = text.removeprefix("EMAIL ").removesuffix(" OK")
        assert TOKEN_RE.fullmatch(token)
        assert decrypt(token, keyring) == "john.smith@example.com"
        assert counts["email"] == 1

    def test_partial_attribute_redaction(self, keyring: Keyring) -> None:
        body = f'<PNR_Retrieve xmlns="{NS}"><Remark data="contact john@example.com ok"/></PNR_Retrieve>'.encode()
        redacted, counts = redact_response_body(
            body,
            channel="mock",
            ruleset=_extract_ruleset(path="//m:Remark/@data", method="replace", replacement="[email]"),
            keyring=keyring,
        )
        value = parse_bytes(redacted).xpath("//*[local-name()='Remark']/@data")[0]
        assert value == "contact [email] ok"
        assert counts["email"] == 1

    def test_required_missing_path_fails_closed(self, keyring: Keyring) -> None:
        body = _doc("John Smith", "EMAIL john.smith@example.com OK")
        with pytest.raises(RedactionError):
            redact_response_body(
                body,
                channel="mock",
                ruleset=_extract_ruleset(path="//m:Missing", required=True),
                keyring=keyring,
            )

    def test_required_extract_no_match_fails_closed(self, keyring: Keyring) -> None:
        body = _doc("John Smith", "NO EMAIL HERE")
        with pytest.raises(RedactionError):
            redact_response_body(body, channel="mock", ruleset=_extract_ruleset(required=True), keyring=keyring)


class TestEmbeddedDeanonymization:
    def test_embedded_token_round_trips(self, keyring: Keyring) -> None:
        token = encrypt("JOHN SMITH", keyring)
        body = f"<r><Note>PSGR {token} RQ WCHR</Note></r>".encode()
        out, count = deanonymize_request_body(body, keyring=keyring)
        assert count == 1
        assert parse_bytes(out).xpath("//Note")[0].text == "PSGR JOHN SMITH RQ WCHR"

    def test_token_adjacent_to_punctuation(self, keyring: Keyring) -> None:
        token = encrypt("Jane", keyring)
        body = f"<r><Note>NAME: {token}, CONFIRMED</Note></r>".encode()
        out, count = deanonymize_request_body(body, keyring=keyring)
        assert count == 1
        assert parse_bytes(out).xpath("//Note")[0].text == "NAME: Jane, CONFIRMED"

    def test_full_value_token_still_round_trips(self, keyring: Keyring) -> None:
        token = encrypt("Solo", keyring)
        body = f"<r><Name>{token}</Name></r>".encode()
        out, count = deanonymize_request_body(body, keyring=keyring)
        assert count == 1
        assert parse_bytes(out).xpath("//Name")[0].text == "Solo"

    def test_embedded_lookalike_left_untouched(self, keyring: Keyring) -> None:
        body = b"<r><Note>Plain Name ENC_not a token</Note></r>"
        out, count = deanonymize_request_body(body, keyring=keyring)
        assert count == 0
        assert parse_bytes(out).xpath("//Note")[0].text == "Plain Name ENC_not a token"

    def test_full_value_bad_token_fails_closed(self, keyring: Keyring) -> None:
        body = b"<r><Name>ENC_dG9vc2hvcnQ</Name></r>"
        with pytest.raises(DeanonymizationError):
            deanonymize_request_body(body, keyring=keyring)
