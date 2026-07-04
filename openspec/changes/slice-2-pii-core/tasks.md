# Tasks: slice-2-pii-core

## 1. Crypto keyring (T2.1)

- [x] 1.1 `uv add cryptography`; TDD red: keyring tests (valid load, epoch 0–15 bounds, 32-byte
      check, file-over-env precedence, active-epoch resolution incl. missing-epoch abort, HKDF
      determinism/domain separation, wrong-key negative, no key material in error strings)
- [x] 1.2 Implement `pii/crypto.py` (Keyring, HKDF `K_enc` derivation, typed errors) + config
      settings `RELAY_PII_KEYRING`, `RELAY_PII_KEY_EPOCH_ACTIVE` in `config/models.py`; startup
      abort when PII enabled without valid keyring (readiness reason); commit

## 2. Token codec + smaz (T2.2)

- [x] 2.1 Vendor pure-Python smaz (`pii/smaz.py`) with canonical codebook; round-trip + pinned
      vector tests
- [x] 2.2 TDD red: codec property tests (unicode round-trip, IV uniqueness, token regex
      `^ENC_[A-Za-z0-9_-]+$`, size bound raw+13B pre-base64, compress flag set/clear, truncated/
      malformed/unknown-epoch/reserved-bits typed failures)
- [x] 2.3 Implement `pii/codec.py` (encrypt/decrypt, control byte, AES-256-CTR `iv‖0x00000000`,
      compress-if-smaller); commit

## 3. Hardened XML ops (T2.3)

- [x] 3.1 `uv add lxml` (verify musllinux wheel in Alpine build); TDD red: attack suite (XXE file
      read, billion-laughs, external DTD, DOCTYPE reject, depth/node/byte limits, malformed) +
      error-type mapping tests (413 oversize, 502 structural/parse)
- [x] 3.2 Implement `pii/xml_ops.py` (parser factory, raising resolver, limit-enforcing
      `parse_bytes`, typed errors, `xml_parse_errors_total{kind}` hook); commit

## 4. Rules model + loader (T2.4)

- [x] 4.1 TDD red: rule model tests (encrypt/mask/replace/remove variants, discriminated required
      params, unknown method rejects ruleset, extra keys forbidden, regex compile-at-load, flat
      wire format folding, generated JSON Schema shape)
- [x] 4.2 Implement `pii/rules.py` models + flat-wire validator + JSON Schema generation (extend
      `config/json_schema.py` pattern)
- [x] 4.3 TDD red: loader tests (fetch ok, timeout→fallback, bad schema_version→fallback,
      malformed JSON→fallback, invalid baked bundle aborts when PII enabled, no polling) with
      httpx MockTransport
- [x] 4.4 Implement startup fetch (single attempt, no retries) + baked `rules_fallback.json` +
      `RELAY_RULES_API_URL` setting + `rule_version` gauge; wire into lifespan; commit

## 5. Redaction engine — response (T2.5)

- [x] 5.1 Author synthetic sanitized golden fixtures under `tests/fixtures/mock/` (SOAP + plain
      XML request/response pairs with expected redacted output per action type)
- [x] 5.2 TDD red: generic operation parser tests (SOAP body child, root element, header ignored);
      engine tests (rule select by channel+operation, ignored patterns, unknown ns prefix
      no-match + metric, per-action golden tests with decrypt-and-compare, structure/namespace
      preservation, pii-disabled byte-identical pass-through, mid-document failure → 502
      `pii_redaction_failed` with no partial body)
- [x] 5.3 Implement `pii/engine.py` redaction + generic operation parser; wire response hook in
      forwarder (before response header hygiene); commit

## 6. De-anonymization engine — request (T2.6)

- [x] 6.1 TDD red: scan/replace tests (text + attribute tokens, non-token values untouched, bad
      token → 502 `pii_deanonymization_failed`, request never forwarded on failure); e2e
      round-trip test (mock channel: redacted response token → later request → mock asserts
      plaintext received)
- [x] 6.2 Implement de-anonymization in `pii/engine.py`; wire request hook in forwarder; commit

## 7. PII metrics + close-out (T2.7)

- [x] 7.1 TDD red then implement: `pii_fields_redacted_total{channel,pii_type}`,
      `pii_fields_decrypted_total{channel}`, `xml_parse_errors_total{channel,kind}`,
      `rule_version` in `observability/metrics.py`; assert via in-memory reader; log-cleanliness
      test (no PII/tokens/keys in captured logs); commit
- [x] 7.2 Docs parity: the relay-configuration spec check (keyring/epoch/rules URL), README PII note; `just ci`
      green + coverage ≥85%; pre-commit all-files; mark OpenSpec task lists T2 complete
- [x] 7.3 Run end-of-file-fixer before archive; `openspec archive slice-2-pii-core`; final commit
