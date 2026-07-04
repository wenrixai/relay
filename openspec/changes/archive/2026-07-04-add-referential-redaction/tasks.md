## 1. Rule schema — reference kind

- [x] 1.1 Write failing tests in `tests/unit/test_pii_rules.py` (or the rules test module): valid
      reference rule loads; empty `source_pii_types` rejected; unknown source pii_type rejected;
      mixed field+reference ruleset loads; bad regex in reference `operation` rejected at load;
      generated JSON Schema encodes the `rule_type` discriminator + reference required params.
- [x] 1.2 Add `ReferenceRule` (pydantic v2, `extra="forbid"`, `rule_type: Literal["reference"]`)
      with `source_pii_types` (non-empty `list[PiiType]`), `pii_type`, `min_match_len` (int ≥1,
      default 3), `word_boundary` (bool, default true), and `action` (encrypt in v1).
- [x] 1.3 Make `RuleSet.rules` a discriminated union on `rule_type` (`FieldRule | ReferenceRule`),
      keeping `field` as the implied default for backward compatibility.
- [x] 1.4 Confirm `generate_rules_json_schema()` emits the discriminator; run the schema test green.

## 2. Engine — value collection (phase 1)

- [x] 2.1 Write failing tests: field-rule matches are collected into `pii_type` buckets as
      plaintext BEFORE the node is rewritten; buckets are empty when nothing matches; no persistence
      across calls.
- [x] 2.2 In `redact_response_body`, capture the located plaintext value into a
      `dict[PiiType, set[str]]` collector during field-rule iteration, before `_apply_action`.

## 3. Engine — reference redaction (phase 2)

- [x] 3.1 Write failing tests: name scrubbed from a remark node (round-trip decrypts); search bounded
      to target path (other nodes untouched); unknown namespace prefix no-match + warning metric.
- [x] 3.2 Write failing guard tests: value shorter than `min_match_len` skipped; `word_boundary`
      prevents "John"→"Johnson"; case-insensitive match preserves surrounding casing.
- [x] 3.3 Implement `select_rules` to return field and reference rules (kind-aware) and add a
      phase-2 pass that, per reference rule, locates target nodes and splices `encrypt` tokens over
      each guarded literal span in `node.text` (structural edit; value escaped; fresh token per hit).
- [x] 3.4 Wire `pii_fields_redacted_total` attribution for reference redactions; test the count.
- [x] 3.5 Fail-closed test: encrypt failure mid free-text → `RedactionError` → 502
      `pii_redaction_failed`, no partial body.

## 4. Engine — embedded de-anonymization

- [x] 4.1 Write failing tests: embedded token round-trip; token adjacent to punctuation decrypts;
      non-token values untouched; malformed embedded token → `DeanonymizationError` (502); existing
      full-match round-trip still passes.
- [x] 4.2 Change `deanonymize_request_body` from `TOKEN_RE.fullmatch` to a `TOKEN_RE.finditer`
      span-splice over text and attribute values; keep fail-closed error wrapping.

## 5. Fixtures, docs, quality gate

- [x] 5.1 Add a sanitized Amadeus/Sabre remark fixture under `tests/fixtures/` and an integration
      round-trip test (redact response → send remark token back → channel gets plaintext).
- [x] 5.2 Update the baked fallback bundle only if needed; document the `reference` rule in the relay-configuration spec
      and the `pii-rule-authoring` skill (over-redaction caution, guard defaults).
- [x] 5.3 Run `just ci` green (ruff, mypy strict, pylint, full test suite, coverage gate ≥85%);
      `openspec validate --change add-referential-redaction --strict`.
