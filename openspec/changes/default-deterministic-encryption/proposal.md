## Why

Random-IV CTR is today's default encrypt mode, so the same passenger encrypts to a different
`ENC_` token in every response. Callers cannot correlate, deduplicate, or cache a redacted value
across responses — the relay's own verification shows 0 token overlap between two passes over an
identical Amadeus payload — and none of the 100 `encrypt` rules in `rules_fallback.json` opts into
the deterministic mode that would fix it. Making deterministic encryption the default gives every
rule stable tokens without a 100-rule edit, and the AES-SIV code path plus its control-bit signal
have shipped in every tagged relay since before v1.0.0, so no deployed relay rejects them.

## What Changes

- **BREAKING** (behavioral, not wire-format): `encrypt` actions default to deterministic AES-256-SIV
  under `K_siv` instead of random-IV AES-256-CTR under `K_enc`. Emitted tokens now carry control-byte
  bit 5 by default, and the same plaintext yields a byte-identical token across responses, processes,
  and pod restarts, for as long as the master key is unchanged.
- **BREAKING** (privacy posture): token equality becomes an observable property of *all* encrypted
  fields rather than an opt-in per rule. An observer without the key can now tell that two redacted
  fields hold the same value. This was previously described in the codec as "a deliberate, bounded
  leak (opt-in per rule)"; it is now the default and is bounded only by rules that opt out.
- Per-rule `"deterministic": false` becomes the opt-out and is the only way to get random-IV tokens.
- `codec.encrypt(...)` flips its `deterministic` keyword default to `True`; `decrypt` is untouched —
  it already routes on bit 5 and needs no rule or configuration knowledge.
- No new configuration surface: no env var, no `relay.json` field, no rules-file edit. Existing
  rulesets keep loading unchanged; they simply mint deterministic tokens.
- Outstanding random-IV tokens minted before this change keep decrypting exactly as before.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `token-codec`: the codec's default encryption mode becomes deterministic AES-SIV; the "IV
  uniqueness in default mode" and "Non-deterministic … SHALL remain the default mode" requirements
  invert.
- `pii-rules`: the `encrypt` action's `deterministic` field default changes from false to true, and
  the flag is now an opt-*out* request rather than an opt-in.
- `redaction-engine`: intra-pass cache behavior is unchanged, but the scenario that names random-IV
  the "default mode" is re-labelled so the spec does not contradict `token-codec`.

## Impact

- `src/channel_relay/pii/codec.py` — `encrypt` keyword default and module docstring.
- `src/channel_relay/pii/rules.py` — `EncryptAction.deterministic` field default and description.
- `src/channel_relay/pii/engine.py` — comment wording only; `_encrypt_cached` already keys on mode.
- Generated rules JSON Schema (`config/json_schema.py` output) — `default` for `deterministic`.
- `docs/PROJECT.md` §8.4 authoring guidance for `deterministic`.
- Tests asserting the old default (`test_pii_codec.py`, `test_pii_engine.py`, `test_pii_rules.py`)
  must pin `deterministic=False` explicitly where they exercise random-IV behavior.
- Runtime: `K_siv` is now on the hot path for every encrypted field. AES-SIV is two AES passes
  (S2V + CTR) versus CTR's one, on values of a few dozen bytes.
- No migration, no key regeneration, no rules-file change, no deploy ordering constraint.
