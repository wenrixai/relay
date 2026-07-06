## Context

`codec.encrypt` draws a fresh random 96-bit IV per call (`codec.py:49`), so identical plaintext never yields the same `ENC_` token — by design for confidentiality, but it breaks callers that compare PII values by equality across responses (passenger matching, dedup, refund-to-passenger correlation; Gap 5 of `docs/SABRE_INTEGRATION_REVIEW.md`). Even intra-response, reference rules re-encrypt every free-text hit (`engine.py:295`), so a name field and its remark occurrence carry different tokens.

Current token layout: `ENC_ + base64url_nopad(control ‖ iv ‖ ciphertext)`; control bits 0–3 = epoch, bit 4 = compressed, bits 5–7 reserved-zero and rejected on decrypt (`_RESERVED_MASK = 0xE0`). Keyring derives one `K_enc[epoch]` per epoch via HKDF-SHA256 with info `wenrix-pii-enc-v1` (`crypto.py`).

Constraints: never weaken crypto defaults, keep old tokens decryptable, format stays versioned via control bits, fail closed on anything unknown, `cryptography` is already a dependency (ships `AESSIV`).

## Goals / Non-Goals

**Goals:**
- Same plaintext encrypted twice within one redaction pass yields the same token (all modes — fixes intra-response correlation immediately).
- Opt-in per-rule deterministic mode: same plaintext + same epoch yields the same token across responses (AES-SIV).
- Old CTR tokens remain valid forever; deterministic tokens are distinguishable by a control bit and decrypt transparently (de-anonymization stays envelope-driven, no rule knowledge needed).

**Non-Goals:**
- No wholesale SIV enablement — `rules_fallback.json` rollout (which pii_types get `deterministic: true`) is a follow-up gated on Wenrix channels team input.
- No integrity/authentication upgrade for CTR tokens (still confidentiality-only v1).
- No cross-request/persistent token cache — the reuse cache lives and dies with one redaction pass.
- No change to mask/replace/remove or to the de-anonymization request path semantics.

## Decisions

### D1 — AES-SIV (RFC 5297) for deterministic mode, keyed separately

Use `cryptography.hazmat.primitives.ciphers.aead.AESSIV` with a 64-byte key (AES-256-SIV) and **no nonce** — SIV without a nonce is the standard deterministic-encryption construction; the 16-byte synthetic IV doubles as an integrity tag, so deterministic tokens are actually AEAD (a strict upgrade, misuse-resistant). Alternatives rejected: fixed-IV CTR (catastrophic keystream reuse — two ciphertexts XOR to plaintext XOR), HMAC-then-CTR convergent scheme (hand-rolled crypto). Token layout for deterministic tokens: `ENC_ + base64url_nopad(control ‖ siv_ciphertext)` where `siv_ciphertext = tag(16B) ‖ ct` as emitted by `AESSIV.encrypt`. No separate IV field.

### D2 — Control byte bit 5 (`0x20`) = deterministic flag

Bits 5–7 are reserved-zero headroom. Allocate bit 5; `_RESERVED_MASK` narrows `0xE0 → 0xC0`. `decrypt` routes on the flag: clear → CTR path (existing), set → SIV path. Old tokens (bit clear) are untouched; old relay builds reject new deterministic tokens with the existing "reserved control bits set" typed error — fail closed, and it imposes the natural deploy order (relay first, rules flag later). smaz compress-if-smaller applies identically in both modes (compression is a pure function of plaintext, so determinism is preserved); bit 4 keeps its meaning.

### D3 — `K_siv[epoch]` derived from the same master, distinct HKDF info

`Keyring` derives a second per-epoch key: HKDF-SHA256, length 64, info `wenrix-pii-siv-v1`. Same master secret source, zero operational change (no new Secret fields, rotation semantics unchanged — new epoch rotates both derived keys). Derivation is lazy-equivalent cost (one extra HKDF per epoch at load). Alternative rejected: separate keyring entry for SIV keys — doubles secret-management surface for no security gain (HKDF domain separation is exactly for this).

### D4 — Per-pass plaintext→token cache, all encrypt modes

`redact_response` threads a `dict[str, str]` (plaintext → token) alongside the existing collector. `_apply_action`'s encrypt arm and `_redact_reference_rule`'s substitution both consult it before encrypting and record after. Effects: repeated field occurrences of one value share a token; reference-rule hits reuse the phase-1 token (review requirement 2) — for CTR mode this fixes intra-response equality with zero crypto change; for SIV mode it is also a cheap dedup. Cache is keyed on **exact** plaintext (and lives only for the pass — same non-persistence guarantee as the collector). Case-variant occurrences ("John" field vs "JOHN" in a remark, matched case-insensitively by reference rules) intentionally get distinct tokens: encrypting the matched casing preserves round-trip fidelity on de-anonymization, which outranks cross-casing token equality.

Cache key includes the mode: entries are recorded per (plaintext, deterministic-flag) so a deterministic rule and a random-IV rule hitting the same value never share a token (mode is a per-rule contract). Reference rules inherit whichever token phase 1 cached for their exact plaintext only when their own action mode matches; otherwise they encrypt per their own action and cache that.

### D5 — Rules schema: `deterministic: bool = false` on `EncryptAction`

Single optional field, default preserves today's behavior; JSON Schema regenerated from models (never hand-written). Applies to both field and reference rules (both use `EncryptAction`). Per-rule rather than per-pii_type-global: the review's "per pii_type" intent is realized by authoring the flag on the rules of that pii_type — no new global config surface, and mixed policies per operation stay possible.

## Risks / Trade-offs

- [Deterministic tokens reveal equality patterns — same passenger recognizable across responses and over time within an epoch] → This is the property the caller needs; accepted, bounded leak. Mitigations: opt-in per rule, default random-IV CTR, rollout limited to `person` pending Wenrix coordination, epoch rotation re-randomizes the mapping.
- [Old relay instances 502 on new deterministic tokens during a mixed-version deploy] → Fail-closed by design; documented deploy order: ship relay everywhere, then flip `deterministic: true` in rules. No rules in the baked bundle set the flag in this change.
- [SIV tokens are 4 bytes longer than CTR for short values (16B tag vs 12B IV) and dictionary-attackable for low-entropy plaintexts (a known deterministic-encryption property)] → Names/emails have modest entropy but the keyspace is secret; equivalent exposure to any deterministic scheme. Documented in the codec docstring.
- [Per-pass cache changes existing token-shape expectations in tests (two same-value fields now share one token)] → Update affected goldens deliberately; assert the new invariant (equality within pass) rather than the old one.
- [`AESSIV` availability] → `cryptography` ≥ 2.6 ships it; already a pinned dependency. Guard with a unit test importing and round-tripping.

## Migration Plan

1. Land codec/keyring/engine/rules changes with the flag defaulting off — zero behavior change for existing rules except intra-response token reuse (D4), which is a strict transparency improvement.
2. Deploy relay everywhere (all instances able to decrypt SIV tokens).
3. Follow-up change (with Wenrix team): set `deterministic: true` on `person` encrypt rules in `rules_fallback.json` / rules API.
4. Rollback: remove the flag from rules — new tokens revert to CTR; outstanding SIV tokens keep decrypting (decrypt path stays).

## Open Questions

- Which pii_types beyond `person` need cross-response equality? (Wenrix channels team; blocks step 3 only, not this change.)
- Should reference-rule case-insensitive hits normalize casing before cache lookup to gain cross-casing equality at the cost of round-trip casing fidelity? Deferred — current answer is no (D4).
