## Context

PII field crypto (§8.3–8.4, decision D4) ships with key rotation built in via a 1-byte key
epoch: the keyring is `{epoch: master}` (epochs 0–15), one epoch is "active" for new
encryptions (`RELAY_PII_KEY_EPOCH_ACTIVE`, default = highest present), and every token
stamps its epoch into control-byte bits 0–3 so decryption can look up the right key. Old
epochs stay in the keyring so old tokens keep decrypting; retirement is manual.

This mechanism has never been used operationally. Rotation is being redesigned to live in a
KMS store plugin that owns key lifecycle out of band. Keeping the epoch machinery in the
relay in the meantime adds surface (a keyring dict + range validation, an active-epoch
selector, per-epoch HKDF caching, epoch encode/decode in the codec, config + Helm value +
`/admin/flare` fields) with no payoff.

The crypto primitives themselves — AES-256-CTR, AES-256-SIV (deterministic mode),
HKDF-SHA256 derivation of `K_enc`/`K_siv`, smaz compress-if-smaller, the `ENC_` token
framing — are unaffected. This change strips only the rotation/epoch layer wrapped around
them.

## Goals / Non-Goals

**Goals:**
- Remove the epoch/rotation concept from crypto, codec, config, admin diagnostics, specs,
  docs, and the Helm chart.
- Simplify `Keyring` to a single validated master key with one derived `(K_enc, K_siv)`
  pair.
- Preserve all confidentiality/integrity properties and keep pre-existing `ENC_` tokens
  decryptable.
- Keep the deploy story unchanged where it isn't about rotation: create-if-absent Secret,
  no key regeneration on `helm upgrade`, file-over-inline precedence.

**Non-Goals:**
- Designing the future KMS store plugin or any replacement rotation mechanism.
- Changing cipher algorithms, IV width, HKDF info labels, the deterministic mode, or the
  `ENC_` prefix/regex.
- Migrating or re-encrypting existing stored tokens.

## Decisions

### D1: Keyring source becomes a single base64(32-byte) key, with a one-entry legacy shim
The keyring source (inline `RELAY_PII_KEYRING` or the mounted file) SHALL be a single
base64(32-byte) master key. To avoid forcing every already-provisioned Secret to be
re-created on upgrade, the loader also accepts a **single-entry** legacy
`{"<int>": "<base64>"}` object and uses that one key. A **multi-entry** object is rejected
with a clear error stating rotation was removed.

- *Why:* a bare key is the simplest honest representation once epochs are gone; the
  one-entry shim keeps `helm upgrade` non-breaking for existing single-key installs (which
  is every install, since rotation was never used). Fail-closed on multi-entry keeps the
  "no silent key selection" security posture.
- *Alternatives:* (a) keep the `{epoch: key}` JSON and ignore epoch keys — rejected, leaves
  the dead concept in the format; (b) bare key only, no shim — rejected, needlessly breaks
  existing Secrets on upgrade.

### D2: `Keyring` collapses to one derived key pair
Remove `_enc_keys`/`_siv_keys` dicts, `active_epoch`, `epochs`, `UnknownEpochError`, and the
`_MAX_EPOCH` range check. `Keyring` holds one `K_enc` and one `K_siv`; `enc_key()`/`siv_key()`
take no epoch. `load_keyring()` drops its `active_epoch` parameter. HKDF derivation and the
"never log key material" rule are unchanged.

- *Why:* single key ⇒ no lookup, no unknown-epoch path, no active selection.

### D3: Token control byte drops epoch bits; former epoch bits become reserved-zero
`encrypt` writes bits 0–3 as zero (no epoch stamp). The reserved mask widens from `0xC0`
to `0xCF` (bits 0–3 and 6–7 reserved). `decrypt` uses the single key and raises the typed
reserved-bits error if any of bits 0–3 are set.

- *Why:* pre-existing tokens in single-key deployments were all minted under epoch 0 (active
  defaulted to the max present epoch = 0), so their bits 0–3 are already zero and they
  decrypt unchanged. Folding the freed bits into the reserved mask widens version headroom
  and keeps the format self-describing/versioned.
- *Backward-compat bound:* a token minted under epoch ≥ 1 would now fail closed with a
  reserved-bits error. This is acceptable because rotation was never performed; a task
  verifies no such tokens exist before rollout.
- *Alternative:* ignore bits 0–3 on decode (accept any value) — rejected: looser, less
  headroom, and weaker than the project's fail-closed default.

### D4: Config, admin, and deploy surface
Remove `Settings.pii_key_epoch_active` and the `RELAY_PII_KEY_EPOCH_ACTIVE` env var; remove
the Helm `piiKeyring.activeEpoch` value and its `deployment.yaml` env wiring; drop the
`active_epoch`/`epochs`/`pii_key_epoch_active_configured` fields from `/admin/flare`. The
Helm Secret template generates a bare base64 key instead of a `{"0": key}` object.

## Risks / Trade-offs

- **Existing Secret uses `{"0": "..."}` JSON after upgrade** → the one-entry legacy shim
  (D1) parses it, so no re-provisioning is required. New installs get a bare key.
- **An epoch ≥ 1 token exists somewhere** → it would fail closed (reserved-bits error →
  502). Mitigation: verification task confirms production only ever minted epoch-0 tokens
  before merge; fail-closed (not silent) if the assumption is wrong.
- **Multi-entry keyring Secret in the wild** → rejected at startup with a clear message
  (fail-closed), rather than silently picking a key.
- **Future KMS plugin needs epochs back** → it will define its own key-selection format;
  the widened reserved bits (D3) leave headroom to reintroduce a version/epoch field
  cleanly.

## Migration Plan

1. Confirm no `ENC_` tokens minted under epoch ≥ 1 exist in production (single-key
   deployments only ever used epoch 0).
2. Ship code + spec + doc + chart changes together.
3. On `helm upgrade`: existing `{"0": key}` Secret is preserved (create-if-absent) and
   parsed by the legacy shim — no operator action needed. Remove any
   `piiKeyring.activeEpoch` override from custom values.
4. **Rollback:** revert the release; the prior chart re-adds `activeEpoch` and the epoch
   keyring. Tokens minted while the new code was live are epoch-0 and decrypt fine under the
   restored code.

## Open Questions

- None blocking. The KMS store plugin design is tracked separately and is out of scope here.
