## 1. Keyring: K_siv derivation

- [x] 1.1 Write failing unit tests for `Keyring.siv_key(epoch)`: 64-byte output, deterministic across loads, differs per epoch, distinct from `K_enc` (domain separation), raises `UnknownEpochError` for missing epoch, never logged
- [x] 1.2 Implement `_derive_siv_key` (HKDF-SHA256, length 64, info `wenrix-pii-siv-v1`) and `Keyring.siv_key()` in `src/channel_relay/pii/crypto.py`; derive at load alongside `K_enc`

## 2. Codec: deterministic SIV mode

- [x] 2.1 Write failing unit tests for deterministic mode: byte-identical tokens for same plaintext+epoch, round-trip, different plaintexts differ, epoch rotation changes tokens (both still decrypt), token matches `^ENC_[A-Za-z0-9_-]+$`, tampered ciphertext raises `TokenError` (SIV auth), truncated deterministic token raises `TokenError`, smaz compressed/uncompressed round-trips, legacy CTR tokens still decrypt, bits 6–7 set still rejected
- [x] 2.2 Implement in `src/channel_relay/pii/codec.py`: `_DETERMINISTIC_FLAG = 0x20`, narrow `_RESERVED_MASK` to `0xC0`, `encrypt(..., deterministic=False)` SIV path via `cryptography` `AESSIV` (no nonce, `K_siv[epoch]`, layout `control ‖ tag ‖ ct`), `decrypt` routing on the flag with mode-specific min-length checks
- [x] 2.3 Update codec module docstring: token layout variants, deterministic equality-leak trade-off, deploy-order note (old relays reject SIV tokens fail-closed)

## 3. Rules: `deterministic` flag on EncryptAction

- [x] 3.1 Write failing unit tests: `deterministic` defaults false, `deterministic: true` loads on field and reference encrypt rules, `deterministic` on mask/replace/remove rejects the ruleset, generated JSON Schema documents the flag
- [x] 3.2 Add `deterministic: bool = False` to `EncryptAction` in `src/channel_relay/pii/rules.py`; regenerate the rules JSON Schema artifact

## 4. Engine: per-pass token cache

- [x] 4.1 Write failing unit/integration tests: two encrypt-rule nodes with identical plaintext share one token; distinct plaintexts differ; reference hit reuses the phase-1 field token; repeated reference hits share a token and count each occurrence; case-variant reference hit gets its own token that decrypts with matched casing; deterministic vs non-deterministic rules on same plaintext yield different tokens; two separate passes on the same body yield different tokens in default mode; cache never appears in logs
- [x] 4.2 Implement pass-scoped `dict[tuple[str, bool], str]` cache in `src/channel_relay/pii/engine.py`, threaded through `_apply_action` (encrypt arm) and `_redact_reference_rule` (lookup before `encrypt`, record after); pass the rule's `deterministic` flag into codec calls; `force_redact` path unaffected
- [x] 4.3 Fix any existing golden/integration tests that asserted token inequality for repeated values within one response — assert the new intra-pass equality invariant instead

## 5. Verification & docs

- [x] 5.1 Cross-mode e2e test: response redacted with a deterministic `person` rule twice (two requests) yields identical tokens across responses; a follow-up request carrying either token de-anonymizes to the plaintext through the unchanged envelope-driven path
- [x] 5.2 Add rules-authoring guidance to the PII docs: when to set `deterministic: true` (caller equality needs), the bounded equality-leak trade-off, rollout order (relay deploy before rules flag flip); note `rules_fallback.json` is intentionally unchanged in this change
- [x] 5.3 Run `just ci` (lint, fmt-check, mypy strict, pylint, full test suite) and `openspec validate --changes deterministic-pii-tokens`
