# Tasks — cover mixed-content tail text; make the keyring guard explicit

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_pii_engine.py`: request with an `ENC_` token in `<a/>ENC_…<b/>` tail → decrypted in place; channel receives plaintext (currently skipped).
- [ ] 1.2 Full-value token in tail that fails to decrypt → 502 `pii_deanonymization_failed`.
- [ ] 1.3 Reference-rule redaction: a collected name appearing in a target node's tail text → encrypted.
- [ ] 1.4 Fail-closed test for the keyring guard that does NOT depend on `assert` (e.g. patch to simulate the optimized path, or assert an explicit `RedactionError`).

## 2. Implementation

- [ ] 2.1 `deanonymize_request_body`: also process `element.tail` with `_deanonymize_value`.
- [ ] 2.2 `_redact_reference_rule` (and field-rule handling where a rule targets tail): apply the same matching to `.tail`.
- [ ] 2.3 Replace `assert ctx.keyring is not None` at both sites with `if ctx.keyring is None: raise RedactionError(...)`.

## 3. Verify

- [ ] 3.1 Targeted suites green; run once under `PYTHONOPTIMIZE=1` to confirm the guard still fires.
- [ ] 3.2 `openspec validate redact-mixed-content-tail-text --strict`.
- [ ] 3.3 `just ci` green.
