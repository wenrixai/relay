# Design: slice-2-pii-core

## Context

Slice 1 shipped the transparent relay (routing, header hygiene, content classification, error
contract, auth, observability, image/CI). Slice 2 adds the PII core per PROJECT.md §7–§9: encrypt
PII fields in channel responses into `ENC_` tokens, decrypt tokens in later requests, all gated per
channel by `pii.enabled`. Locked decisions D1–D7 constrain the crypto, token format, XML handling,
and rule delivery. Everything lands in `src/channel_relay/pii/` plus hooks in the forwarder.

Request/response flow:

```
response: channel → xml_ops.parse (hardened) → op parse → rule select (channel+operation)
          → XPath locate → skip ignored patterns → action (encrypt/mask/replace/remove)
          → re-serialize → client
request:  client → xml_ops.parse → scan text/attrs for ^ENC_ → decode → epoch → keyring
          → CTR-decrypt → smaz-decompress if flagged → replace → re-serialize → channel
```

## Goals / Non-Goals

**Goals:**
- T2.1–T2.7: keyring, codec, hardened XML ops, rules model + loader, redaction engine,
  de-anonymization engine, PII metrics.
- Fail-closed semantics: never forward partially processed PII (502 per error contract).
- Rules schema validated by pydantic with generated JSON Schema; extensible action set.

**Non-Goals:**
- Per-channel operation parsers and credential swap (Slice 3).
- JSONPath rule execution (model accepts `jsonpath`; engine skips — O6), free-text/Presidio (T6.3),
  `pii_ref` correlation (T6.4), authorization (T4.1).
- Authenticated encryption (confidentiality-only in v1 per D1; format versioned for later).

## Decisions

1. **smaz vendored pure-Python** (`pii/smaz.py`). Alternatives: C-extension bindings (no reliable
   musllinux wheels for the Alpine image; adds builder complexity), PyPI pure-Python packages
   (unmaintained). PII fields are short strings; pure-Python cost is negligible. Vendoring pins the
   canonical antirez codebook and keeps the supply chain clean.
2. **Rules-API contract defined by us pending O3**: `GET {RELAY_RULES_API_URL}` with the relay's
   basic-auth credentials, response = §8.1 JSON document. Single attempt, short timeout, no retries
   (D12 discipline applies to rules fetch too). Alternative — blocking on O3 — stalls the slice;
   the fetch client is small and isolated in `rules.py` if the contract shifts.
3. **Action extensibility via pydantic discriminated union** on `method`: `encrypt` | `mask`
   (`mask_char`, `keep_prefix`) | `replace` (`replacement`) | `remove`. Wire format stays flat
   (§8.1); a `model_validator(mode="before")` folds `method` + params into an internal `action`
   field. Engine dispatches on the action type. Alternative — a single model with optional
   per-method fields — loses per-method required-param validation and produces vague errors.
4. **Strict rule validation, fail closed**: `extra="forbid"`, unknown `method` or bad regex
   invalidates the whole fetched ruleset → baked fallback. Rationale: silently skipping a rule is
   silently not redacting a field. Forward compatibility flows through `schema_version`, not lax
   parsing. Regexes compile at validation time, never per request.
5. **Only `encrypt` is reversible.** `mask`/`replace`/`remove` are one-way; de-anonymization is
   envelope-driven (`^ENC_[A-Za-z0-9_-]+$` full match) and needs no rules, so it naturally only
   reverses encrypt tokens.
6. **Generic operation parser for this slice**: SOAP Body first-child local-name, else document
   root local-name. Lives behind a small function the Slice-3 channel registry will replace.
   Golden fixtures are synthetic sanitized XML under `tests/fixtures/mock/` (no real channel data
   needed yet).
7. **Keyring format** `{epoch_int: base64(32B)}` from `RELAY_PII_KEYRING` (inline JSON) or mounted
   file (file wins), matching the relay-configuration spec. Epochs 0–15 (4 control-byte bits). HKDF-SHA256 with fixed
   info string derives `K_enc`; master keys never used directly, never logged.
8. **Redaction golden tests compare structurally**, not byte-for-byte: IVs are random, so tests
   decrypt produced tokens and compare plaintext + document structure against the expected fixture.
9. **Pipeline placement**: de-anonymization runs after content decode on the request path (stage 7
   position); redaction runs on the response before response header hygiene (stage 9). Both live as
   forwarder hooks, not new middleware classes, to keep buffering decisions (gzip decode, body cap)
   in one place with the existing content stage.

## Risks / Trade-offs

- [Rules-API contract may differ when O3 resolves] → fetch isolated in one function with mocked
  transport tests; wire-format change is a small diff.
- [Vendored smaz drift] → canonical codebook is frozen upstream; round-trip vectors pinned in tests.
- [lxml musllinux wheel availability on Alpine/py3.13] → verify at `uv add` time and in the image
  build; fallback per PROJECT.md §13.1 is build-stage-only compiler deps.
- [Generic operation parser mismatches a future per-channel parser] → rules for real channels ship
  in Slice 3 alongside the real parsers; this slice's rules target mock fixtures only.
- [Structural re-serialization altering insignificant XML details (whitespace, attribute order)]
  → golden tests assert canonical/structural equality; document that byte-identity is not
  guaranteed once a channel opts into PII.
- [CTR with random 96-bit IV: birthday risk at extreme volumes] → per D1/D2 accepted for v1;
  epoch rotation bounds key usage.

## Migration Plan

Additive; PII off by default, so existing deployments are unaffected. Enabling PII on a channel
requires: keyring Secret provisioned (Helm create-if-absent lands in T5.2; env/file works now),
`pii.enabled: true`, and rules covering the channel. Rollback = disable the flag; outstanding
`ENC_` tokens in client hands decrypt as long as their epoch stays in the keyring.

## Open Questions

- O3: real rules-API URL/auth/shape (assumption documented above).
- O6: JSONPath execution timing (model ready, engine deferred).
- Exact Wenrix-default value for `RELAY_RULES_API_URL` (config placeholder until O3).
