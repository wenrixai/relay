## Why

The PII crypto subsystem carries a built-in key-rotation mechanism (an epoch-indexed
keyring, an active-epoch selector, and 4 epoch bits in every token's control byte) that
has never been operationally exercised. Rotation will be reintroduced later through a
dedicated KMS store plugin that owns key lifecycle. Until then the epoch machinery is dead
weight: it complicates the keyring, the token format, config, and the Helm chart, and it
implies an operational procedure that no longer reflects the intended design. Removing it
now shrinks the crypto surface and clears the way for the KMS-based design.

## What Changes

- **BREAKING (keyring format):** the PII keyring source becomes a single base64(32-byte)
  master key instead of a `{epoch_int: base64}` JSON object. A one-entry legacy
  `{"0": "<base64>"}` document is still accepted (so already-provisioned Secrets keep
  working on upgrade); a multi-entry document is rejected with a clear "rotation removed"
  error.
- Collapse `Keyring` to a single derived `(K_enc, K_siv)` pair — remove the epoch dict,
  `active_epoch`, `UnknownEpochError`, and the 0–15 epoch range check.
- **BREAKING (config):** remove the `RELAY_PII_KEY_EPOCH_ACTIVE` setting
  (`pii_key_epoch_active`) and its Helm value `piiKeyring.activeEpoch` / the
  `RELAY_PII_KEY_EPOCH_ACTIVE` env var.
- Token control byte: encrypt no longer stamps an epoch (bits 0–3 written as zero); the
  former epoch bits fold into the reserved-must-be-zero mask, widening version headroom.
  Decrypt uses the single key and rejects any nonzero former-epoch bits fail-closed.
  Pre-existing tokens (all minted under epoch 0 in single-key deployments) still decrypt.
- Remove the `/admin/flare` `active_epoch` / `epochs` / `pii_key_epoch_active_configured`
  diagnostics.
- Keep the crypto primitives unchanged: AES-256-CTR, AES-256-SIV, HKDF-SHA256 derivation,
  smaz compress-if-smaller, the `ENC_` prefix/regex, IV width, and Secret-file/inline
  key loading precedence.
- Remove all rotation documentation and procedures (specs, `docs/`, Helm README/NOTES,
  terraform/cloudformation comments).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `crypto-keyring`: drop the "Active epoch selection" requirement and the epoch-indexed
  keyring shape; the keyring becomes a single validated master key; HKDF derivation and
  secret-loading requirements stay, minus epoch wording.
- `token-codec`: control byte no longer carries key-epoch bits (bits 0–3 become reserved
  zero); decode-failure and deterministic-mode requirements drop their epoch references.
- `deployment-ci`: the "PII key provisioning survives upgrade" requirement drops the
  epoch-rotation documentation clause (create-if-absent + no-regenerate-on-upgrade stays).
- `relay-configuration`: the "PII configuration settings" requirement drops the
  `RELAY_PII_KEY_EPOCH_ACTIVE` setting and active-epoch wording.
- `redaction-engine`: the "Request de-anonymization" requirement drops the "epoch from the
  control byte" wording (behavior unchanged; the codec no longer reads an epoch).

## Impact

- **Code:** `pii/crypto.py`, `pii/codec.py`, `settings.py`, `main.py` (`build_keyring`),
  `admin.py`.
- **Tests:** `tests/unit/test_pii_crypto.py`, `test_pii_codec.py`, `test_admin.py`,
  `tests/conftest.py`, `tests/deployment/test_helm_chart.py`, `tests/e2e/conftest.py`.
- **Deploy:** Helm `values.yaml`, `templates/deployment.yaml`,
  `templates/secret-pii-keyring.yaml`, `templates/NOTES.txt`, chart `README.md`; terraform
  and cloudformation keyring comments.
- **Docs:** `docs/PROJECT.md`, `docs/SECURITY_POSTURE.md`, `docs/PROXY_CONFIGURATION_GUIDE.md`.
- **No change to:** cipher choice, key derivation, token confidentiality/integrity
  properties, or the rules/redaction engine.
