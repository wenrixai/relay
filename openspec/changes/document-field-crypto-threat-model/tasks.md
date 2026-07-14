# Tasks — document the field-crypto threat model

## 1. Spec + docs

- [ ] 1.1 `SECURITY.md` / `docs/PROJECT.md` §8: state explicitly that the default random-IV CTR token
  mode is confidentiality-only with no integrity/tamper protection; the deterministic SIV mode is the
  authenticated option; AEAD default is a versioned future via the reserved control bits.
- [ ] 1.2 Document volume-based epoch-rotation guidance (safe per-epoch encryption-count threshold for
  the 96-bit IV birthday bound) alongside the existing calendar/rotation docs.

## 2. Optional guardrail (nice-to-have, not required for v1)

- [ ] 2.1 (Optional) emit a warning metric/log when an epoch's encryption count crosses a configured
  fraction of the safe bound, to make volume-based rotation actionable.

## 3. Verify

- [ ] 3.1 `openspec validate document-field-crypto-threat-model --strict`.
- [ ] 3.2 Docs build/links check; no `src/` behavior change expected in v1.
