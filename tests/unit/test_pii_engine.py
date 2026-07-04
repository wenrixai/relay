"""Redaction engine tests: operation parsing, rule application, fail-closed (T2.5)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from channel_relay.pii.codec import TOKEN_RE, decrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import RedactionError, parse_operation, redact_response_body
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mock"


@pytest.fixture(name="keyring")
def keyring_fixture() -> Keyring:
    key = base64.b64encode(bytes([7]) * 32).decode()
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
