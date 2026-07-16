## 1. Pre-flight

- [ ] 1.1 Confirm no `ENC_` tokens minted under epoch ≥ 1 exist in any environment (single-key
  deployments only ever used epoch 0); record the finding in the PR description.

## 2. Crypto keyring (TDD)

- [x] 2.1 Update `tests/unit/test_pii_crypto.py`: bare base64 key loads; single-entry legacy
  `{"0": ...}` loads; multi-entry object rejected with a rotation-removed error; wrong length
  rejected; remove all epoch/active-epoch/`UnknownEpochError` tests.
- [x] 2.2 Rewrite `src/channel_relay/pii/crypto.py`: `Keyring` holds one `K_enc` + one `K_siv`;
  `from_json`/loader accept a bare base64 key or one-entry object (reject multi-entry); drop
  `_enc_keys`/`_siv_keys` dicts, `active_epoch`, `epochs`, `_MAX_EPOCH`, and `UnknownEpochError`;
  `enc_key()`/`siv_key()` take no epoch; `load_keyring()` drops the `active_epoch` param. Keep
  HKDF derivation and the no-log-key-material rule unchanged.

## 3. Token codec (TDD)

- [x] 3.1 Update `tests/unit/test_pii_codec.py`: encrypt writes control bits 0–3 as zero;
  round-trip; decrypt raises on any reserved bit (0–3 or 6–7) set; drop epoch/unknown-epoch tests;
  keep deterministic-mode and legacy-token tests.
- [x] 3.2 Update `src/channel_relay/pii/codec.py`: remove `_EPOCH_MASK` and epoch stamping in
  `encrypt`; widen `_RESERVED_MASK` to `0xCF`; `_decrypt_*_body` and `decrypt` take no epoch and
  use the single key; drop `UnknownEpochError` import/handling. Keep AES-CTR/SIV, IV width, smaz,
  and the `ENC_` prefix/regex unchanged.

## 4. Config, startup, admin

- [x] 4.1 Remove `pii_key_epoch_active` from `src/channel_relay/settings.py`.
- [x] 4.2 Update `src/channel_relay/main.py` `build_keyring` to drop the `active_epoch` argument.
- [x] 4.3 Remove `active_epoch`, `epochs`, and `pii_key_epoch_active_configured` from the
  `/admin/flare` payload in `src/channel_relay/admin.py`; update `tests/unit/test_admin.py`.

## 5. Deployment / Helm

- [x] 5.1 `deployment/helm/chart/templates/secret-pii-keyring.yaml`: generate a bare
  base64(32-byte) key (no `{epoch: key}` wrapper); remove rotation guidance comments.
- [x] 5.2 `deployment/helm/chart/templates/deployment.yaml`: remove the
  `RELAY_PII_KEY_EPOCH_ACTIVE` env var.
- [x] 5.3 `deployment/helm/chart/values.yaml`: remove `piiKeyring.activeEpoch` and its rotation
  comment.
- [x] 5.4 `deployment/helm/chart/templates/NOTES.txt` and `README.md`: remove the epoch-rotation
  section and active-epoch references.
- [x] 5.5 Update `tests/deployment/test_helm_chart.py`: assert rendered Secret is a bare key and
  no `RELAY_PII_KEY_EPOCH_ACTIVE` / `activeEpoch` appears.
- [x] 5.6 Remove epoch/rotation keyring comments from `deployment/terraform/*` and
  `deployment/cloudformation/wenrix-relay.yaml`.

## 6. Docs

- [x] 6.1 `docs/PROJECT.md`: remove rotation lines (§ rotation via epoch, D4 wording, upgrade
  rotation note); keep create-if-absent + no-regenerate wording.
- [x] 6.2 `docs/SECURITY_POSTURE.md`: remove the "Rotation" section / epoch wording.
- [x] 6.3 `docs/PROXY_CONFIGURATION_GUIDE.md`: remove the "Key rotation uses integer epochs"
  section and describe the single-key keyring.

## 7. Test fixtures / conftest

- [x] 7.1 Update `tests/conftest.py` and `tests/e2e/conftest.py` keyring fixtures to the
  single-key format; ensure no fixture sets an active epoch.

## 8. Verify

- [x] 8.1 `just ci` green (lint, types, pylint, full suite, coverage ≥ 85%).
- [x] 8.2 `just helm-test` green (chart lint + render + assertions).
- [x] 8.3 `openspec validate remove-key-rotation` passes; run `/verify` on the PII de-anon +
  redaction round-trip to confirm tokens still encrypt/decrypt end-to-end.
- [x] 8.4 Grep the repo for residual `epoch` / `rotat` / `activeEpoch` /
  `RELAY_PII_KEY_EPOCH_ACTIVE` references (excluding `openspec/changes/archive/`) — none remain
  outside intended history.
