"""Rule schema validation tests: discriminated actions, strict policy (T2.4, §8.1)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from channel_relay.pii.rules import (
    EncryptAction,
    ExtractPattern,
    FieldRule,
    MaskAction,
    ReferenceRule,
    RemoveAction,
    ReplaceAction,
    RuleSet,
    generate_rules_json_schema,
)


def rule(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "mock.op.person.001",
        "channel": "mock",
        "operation": "^PNR_Retrieve$",
        "path": "//ns:Traveler/ns:Name",
        "path_type": "xpath",
        "rule_type": "field",
        "pii_type": "person",
        "method": "encrypt",
    }
    base.update(overrides)
    return base


def ref_rule(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "mock.op.ref.001",
        "channel": "mock",
        "operation": "^PNR_Retrieve$",
        "path": "//m:Remark/m:Text",
        "path_type": "xpath",
        "rule_type": "reference",
        "source_pii_types": ["person"],
        "pii_type": "person",
        "method": "encrypt",
    }
    base.update(overrides)
    return base


def ruleset(*rules: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1.0", "rules_version": "2026-07-01", "rules": list(rules)}


def test_valid_encrypt_rule_loads() -> None:
    loaded = RuleSet.model_validate(ruleset(rule()))
    assert isinstance(loaded.rules[0].action, EncryptAction)
    assert loaded.rules[0].pii_type == "person"


def test_method_defaults_to_encrypt() -> None:
    data = rule()
    del data["method"]
    loaded = RuleSet.model_validate(ruleset(data))
    assert isinstance(loaded.rules[0].action, EncryptAction)


def test_encrypt_deterministic_defaults_true() -> None:
    """An encrypt rule that never mentions the flag requests deterministic encryption."""
    action = RuleSet.model_validate(ruleset(rule())).rules[0].action
    assert isinstance(action, EncryptAction)
    assert action.deterministic is True


def test_encrypt_deterministic_opt_out_loads_on_field_rule() -> None:
    action = RuleSet.model_validate(ruleset(rule(deterministic=False))).rules[0].action
    assert isinstance(action, EncryptAction)
    assert action.deterministic is False


def test_encrypt_deterministic_opt_out_loads_on_reference_rule() -> None:
    ref = RuleSet.model_validate(ruleset(ref_rule(deterministic=False))).rules[0]
    assert isinstance(ref, ReferenceRule)
    assert ref.action.deterministic is False


def test_encrypt_deterministic_flag_loads_on_field_rule() -> None:
    action = RuleSet.model_validate(ruleset(rule(deterministic=True))).rules[0].action
    assert isinstance(action, EncryptAction)
    assert action.deterministic is True


def test_encrypt_deterministic_flag_loads_on_reference_rule() -> None:
    ref = RuleSet.model_validate(ruleset(ref_rule(deterministic=True))).rules[0]
    assert isinstance(ref, ReferenceRule)
    assert ref.action.deterministic is True


@pytest.mark.parametrize("method", ["mask", "remove"])
def test_deterministic_on_non_encrypt_method_rejected(method: str) -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(method=method, deterministic=True)))


def test_deterministic_on_replace_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(method="replace", replacement="X", deterministic=True)))


def test_generated_schema_documents_deterministic_flag() -> None:
    assert "deterministic" in str(generate_rules_json_schema())


def test_generated_schema_records_deterministic_default_true() -> None:
    """The published schema must advertise the new default, not just the property."""
    schema = generate_rules_json_schema()
    encrypt_action = schema["$defs"]["EncryptAction"]
    assert encrypt_action["properties"]["deterministic"]["default"] is True


def test_mask_rule_with_params() -> None:
    loaded = RuleSet.model_validate(ruleset(rule(method="mask", mask_char="#", keep_prefix=2)))
    action = loaded.rules[0].action
    assert isinstance(action, MaskAction)
    assert action.mask_char == "#"
    assert action.keep_prefix == 2


def test_replace_rule_requires_replacement() -> None:
    with pytest.raises(ValidationError, match="replacement"):
        RuleSet.model_validate(ruleset(rule(method="replace")))
    loaded = RuleSet.model_validate(ruleset(rule(method="replace", replacement="REDACTED")))
    action = loaded.rules[0].action
    assert isinstance(action, ReplaceAction)
    assert action.replacement == "REDACTED"


def test_remove_rule() -> None:
    loaded = RuleSet.model_validate(ruleset(rule(method="remove")))
    assert isinstance(loaded.rules[0].action, RemoveAction)


def test_unknown_method_rejects_ruleset() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(), rule(method="rot13")))


def test_extra_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(surprise="x")))
    bad_top = ruleset(rule())
    bad_top["extra_top"] = True
    with pytest.raises(ValidationError):
        RuleSet.model_validate(bad_top)


def test_action_params_for_wrong_method_rejected() -> None:
    # mask params on an encrypt rule must not silently vanish.
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(method="encrypt", mask_char="#")))


def test_bad_operation_regex_rejected_at_load() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(operation="([unclosed")))


def test_bad_ignored_pattern_rejected_at_load() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(ignored_content_patterns=["^ok$", "([bad"])))


def test_ignored_patterns_precompiled() -> None:
    loaded = RuleSet.model_validate(ruleset(rule(ignored_content_patterns=["^TMX"])))
    first = loaded.rules[0]
    assert isinstance(first, FieldRule)
    assert first.operation_re.match("PNR_Retrieve")
    assert first.ignored_re[0].match("TMX123")


def test_extract_patterns_precompiled() -> None:
    loaded = RuleSet.model_validate(ruleset(rule(extract_patterns=[{"pattern": r"([^\s]+@[^\s]+)"}])))
    first = loaded.rules[0]
    assert isinstance(first, FieldRule)
    assert isinstance(first.extract_patterns[0], ExtractPattern)
    assert first.extract_re[0].search("email john@example.test")


def test_bad_extract_pattern_rejected_at_load() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(extract_patterns=[{"pattern": "([bad"}])))


def test_required_defaults_false_and_can_be_set() -> None:
    loaded = RuleSet.model_validate(ruleset(rule()))
    first = loaded.rules[0]
    assert isinstance(first, FieldRule)
    assert first.required is False

    required = RuleSet.model_validate(ruleset(rule(required=True))).rules[0]
    assert isinstance(required, FieldRule)
    assert required.required is True


def test_unknown_pii_type_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(pii_type="shoe_size")))


@pytest.mark.parametrize("pii_type", ["age", "ip_address"])
def test_extended_personal_data_types_load(pii_type: str) -> None:
    loaded = RuleSet.model_validate(ruleset(rule(pii_type=pii_type)))

    assert loaded.rules[0].pii_type == pii_type


def test_namespaces_accepted() -> None:
    loaded = RuleSet.model_validate(ruleset(rule(namespaces={"m": "urn:mock:pnr"})))
    assert loaded.rules[0].namespaces == {"m": "urn:mock:pnr"}


def test_jsonpath_path_type_rejected_until_json_inspection_is_supported() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(rule(path_type="jsonpath", path="$.traveler.name")))


def test_incompatible_schema_version_rejected() -> None:
    data = ruleset(rule())
    data["schema_version"] = "2.0"
    with pytest.raises(ValidationError, match="schema_version"):
        RuleSet.model_validate(data)


def test_generated_schema_documents_discriminated_actions() -> None:
    schema = generate_rules_json_schema()
    text = str(schema)
    assert "encrypt" in text
    assert "replacement" in text
    assert "mask_char" in text
    assert schema["title"] == "RuleSet"


def test_valid_reference_rule_loads() -> None:
    loaded = RuleSet.model_validate(ruleset(ref_rule()))
    ref = loaded.rules[0]
    assert isinstance(ref, ReferenceRule)
    assert ref.source_pii_types == ["person"]
    assert isinstance(ref.action, EncryptAction)


def test_reference_rule_guard_defaults() -> None:
    ref = RuleSet.model_validate(ruleset(ref_rule())).rules[0]
    assert isinstance(ref, ReferenceRule)
    assert ref.min_match_len == 3
    assert ref.word_boundary is True


def test_reference_empty_source_pii_types_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(ref_rule(source_pii_types=[])))


def test_reference_unknown_source_pii_type_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(ref_rule(source_pii_types=["shoe_size"])))


def test_reference_non_encrypt_method_rejected() -> None:
    # v1: reference action is encrypt-only; a mask method must not silently load.
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(ref_rule(method="mask", mask_char="#")))


def test_reference_bad_operation_regex_rejected_at_load() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(ref_rule(operation="([unclosed")))


def test_reference_extra_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate(ruleset(ref_rule(surprise="x")))


def test_mixed_field_and_reference_ruleset_loads() -> None:
    loaded = RuleSet.model_validate(ruleset(rule(), ref_rule()))
    assert loaded.rules[0].rule_type == "field"
    assert loaded.rules[1].rule_type == "reference"


def test_generated_schema_documents_rule_type_discriminator() -> None:
    text = str(generate_rules_json_schema())
    assert "rule_type" in text
    assert "reference" in text
    assert "source_pii_types" in text
    assert "extract_patterns" in text
    assert "required" in text
