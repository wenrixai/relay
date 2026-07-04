# Proposal: slice-2-pii-core

## Why

Slice 1 shipped a safe transparent relay, but Wenrix still sees traveler PII in readable form.
Slice 2 delivers the privacy-first core: PII fields in channel responses are
encrypted into self-describing `ENC_` tokens before reaching Wenrix, and tokens in later requests
are de-anonymized back to plaintext before reaching the channel. This is the zero-trust value
proposition of v2 (PROJECT.md §7–§8) and blocks Slice 3 (per-channel swap) and Slice 4.

## What Changes

- New `pii/` package: crypto keyring, token codec (+ vendored pure-Python smaz), hardened XML
  parser factory, rules model + loader, redaction/de-anonymization engine.
- Crypto: AES-256-CTR with HKDF-derived `K_enc`, keyring indexed by 1-byte epoch (low 4 bits used),
  master keys from `RELAY_PII_KEYRING` (env or mounted Secret file).
- Token format: `ENC_ + base64url_nopad(control ‖ 96-bit IV ‖ ciphertext)`; smaz
  compress-if-smaller flagged in the control byte. Confidentiality-only in v1 (D1–D3).
- All XML parsing moves behind a hardened lxml factory in `pii/xml_ops.py` (no entities/DTD/
  network; byte/depth/node limits) per PROJECT.md §9.4.
- PII rules: pydantic v2 models with a **discriminated union of actions**
  (`encrypt` | `mask` | `replace` | `remove`); JSON Schema generated from the models; strict
  validation (unknown method/extra keys ⇒ ruleset rejected ⇒ baked fallback). Startup fetch from
  `RELAY_RULES_API_URL` with baked fallback bundle; no polling (D7). Rules-API contract is a
  documented assumption pending O3 (GET + basic auth returning the §8.1 JSON document).
- Redaction on the response path and de-anonymization on the request path, gated per channel by
  `pii.enabled`; any crypto/rule/XML failure returns the defined 502 and never forwards partially
  processed PII.
- Generic XML operation parser (SOAP body child / root element local-name) used for rule selection
  until per-channel parsers land in T3.2; golden fixtures are synthetic sanitized XML for the mock
  channel.
- New metrics: `pii_fields_redacted_total`, `pii_fields_decrypted_total`,
  `xml_parse_errors_total`, `rule_version`.
- New dependencies: `cryptography`, `lxml` (musllinux wheels verified in image build); smaz
  vendored.

No breaking changes; PII stays off by default (zero-config channels unaffected).

## Capabilities

### New Capabilities
- `crypto-keyring`: epoch-indexed keyring, HKDF key derivation, key loading/rotation semantics.
- `token-codec`: `ENC_` token encode/decode, smaz compression, size/uniqueness properties.
- `xml-hardening`: hardened lxml parser factory, limits, attack rejection, error mapping.
- `pii-rules`: rule schema (pydantic, discriminated actions), validation policy, startup fetch +
  baked fallback, generated JSON Schema.
- `redaction-engine`: response redaction, request de-anonymization, per-channel gating, operation
  parsing (generic, v1), failure semantics, PII metrics.

### Modified Capabilities
- `relay-configuration`: new settings `RELAY_PII_KEYRING`, `RELAY_PII_KEY_EPOCH_ACTIVE`,
  `RELAY_RULES_API_URL`; per-channel `pii.enabled` becomes behavior-bearing.
- `error-contract`: 502 `reason` values `pii_redaction_failed`, `pii_deanonymization_failed`,
  `xml_parse_error` become reachable with defined triggers.
- `observability`: four new PII/XML metrics added to the required metric set.

## Impact

- Code: new `src/channel_relay/pii/` (crypto, codec, smaz, xml_ops, rules, engine); forwarder
  request/response hooks; `config/models.py` + generated schema; `observability/metrics.py`;
  baked `rules_fallback.json`; `tests/fixtures/mock/` golden fixtures.
- Dependencies: `cryptography`, `lxml` added via `uv add`; Alpine image must keep musllinux wheels
  (no compiler in final stage).
- Docs: relay-configuration spec parity check (keyring/epoch/rules API already specified), README PII note.
- Security surface: key material handling (never logged/committed), fail-closed redaction, XML
  attack hardening — SECURITY.md threat model unchanged, implementation now enforces it.
