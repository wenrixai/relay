## Why

`encrypt` uses a random 96-bit IV per call, so identical plaintext produces a different `ENC_` token on every occurrence — across responses and even between two fields (or a field and a free-text reference) in the same response. Caller logic that compares PII values by equality — matching a passenger between `GetReservationRS` and `GetPriceQuoteRS`, deduplicating names, correlating a refund document to a passenger — silently degrades (wrong matches / no matches), which is worse than crashing. This is Gap 5 of `docs/SABRE_INTEGRATION_REVIEW.md` and blocks enabling PII for Sabre production traffic.

## What Changes

- **Intra-response token reuse (quick win, no crypto change):** reference rules re-encrypt each free-text hit with a fresh IV today. Cache `plaintext → token` during a redaction pass so a value already tokenized in phase 1 (field rules) reuses the same token in phase 2 (reference rules), and repeated field occurrences of the same plaintext within one response also reuse the token.
- **Deterministic encryption mode (cross-response equality):** add an opt-in `deterministic: true` flag on `encrypt` rules. Deterministic tokens use AES-SIV (RFC 5297, `cryptography.AESSIV`) with a per-epoch SIV key derived from the same master key via HKDF with a distinct `"siv"` info label. Same plaintext + same epoch → same token.
- **Token format versioning:** allocate one reserved control-byte bit (bits 5–7 are reserved-zero today) as the deterministic/SIV flag so `decrypt` routes to the right primitive and all existing CTR tokens stay valid. Decrypt accepts both modes regardless of rule config (de-anonymization is envelope-driven).
- **Documented trade-off:** deterministic encryption reveals equality patterns (same passenger recognizable across responses) — an accepted, bounded leak that is exactly the property the caller needs. Random-IV CTR remains the default; SIV is enabled per rule, starting with `person` fields only, coordinated with the Wenrix channels team.

Non-goals: no change to mask/replace/remove actions; no wholesale SIV enablement; no change to the ENC_ token envelope prefix or the de-anonymization contract.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `token-codec`: token format gains a deterministic (AES-SIV) variant signaled by a control-byte flag; `encrypt` accepts a deterministic mode; `decrypt` routes on the flag and keeps accepting v1 CTR tokens.
- `crypto-keyring`: keyring derives a second per-epoch key, `K_siv` (64 bytes for AES-256-SIV), via HKDF with a distinct `"siv"` domain-separation label; master keys remain the single source.
- `pii-rules`: `EncryptAction` gains an optional `deterministic: bool` field (default `false`); schema regenerated from models.
- `redaction-engine`: within one redaction pass, encrypting the same plaintext must yield the same token (plaintext→token cache shared by field and reference phases).
- `referential-redaction`: reference-rule hits reuse the phase-1 token for the same plaintext instead of re-encrypting with a fresh IV.

## Impact

- `src/channel_relay/pii/crypto.py` — derive and expose `siv_key(epoch)`.
- `src/channel_relay/pii/codec.py` — deterministic flag bit, SIV encrypt path, decrypt routing; reserved-bit validation narrows from 3 bits to 2.
- `src/channel_relay/pii/rules.py` — `EncryptAction.deterministic`; JSON Schema regeneration.
- `src/channel_relay/pii/engine.py` — per-pass token cache threaded through `_apply_action` / `_redact_reference_rule`.
- `rules_fallback.json` — unchanged now; `deterministic: true` rollout for `person` rules is a follow-up gated on Wenrix team input.
- Dependencies: none new (`cryptography` already ships `AESSIV`).
- Backward compatibility: existing tokens decrypt unchanged; old relays reject new SIV tokens as "reserved control bits set" (fail closed) — deploy relays before enabling `deterministic` in rules.
