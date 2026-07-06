## Why

Some customers do not want their PII reversibly encrypted (`ENC_` tokens) at all — they
want a non-reversible placeholder instead, with no key material or de-anonymization
involved. Today the action applied to a field (`encrypt`/`mask`/`replace`/`remove`) is
fixed per rule in the shared rules JSON, so the only way to avoid encryption for one
customer is to fork the ruleset. We need a per-channel override that always substitutes
a fixed placeholder wherever a rule would otherwise encrypt.

## What Changes

- Add `pii.force_redact` (bool, default `false`) to per-channel PII config, alongside
  the existing `pii.enabled`.
- When `force_redact` is `true` for a channel, every `encrypt` action resolves to the
  fixed literal `"REDACTED"` instead of calling the crypto codec — for both `field`
  rules (`EncryptAction`) and `reference` rules (currently hardcoded to `encrypt` only).
  No `ENC_` token is ever produced for that channel.
- A channel that only uses `force_redact` (no other channel needs real encryption) no
  longer forces the deployment to require a configured PII keyring at startup.
- Fail-closed error semantics (502 `pii_redaction_failed` on any redaction failure) are
  unchanged.

## Capabilities

### New Capabilities
(none — this extends existing PII capabilities, no new capability directory)

### Modified Capabilities
- `relay-configuration`: adds the `pii.force_redact` field to per-channel PII config.
- `pii-rules`: the effective outcome of an `encrypt` action can be overridden to a fixed
  placeholder at apply-time by channel config; documents this for both rule kinds.
- `redaction-engine`: describes fixed-placeholder substitution for `encrypt` actions in
  field-rule redaction when a channel forces redact.
- `referential-redaction`: reference rules (hardcoded `encrypt`-only in v1) also honor
  `force_redact`, substituting the same fixed placeholder instead of encrypting.
- `crypto-keyring`: startup SHALL NOT require a keyring solely because a channel has
  `pii.enabled: true` when that channel also has `pii.force_redact: true` (no encryption
  ever occurs for it); a keyring is still required if any channel needs real encryption
  or response-auth encryption.

## Impact

- `src/channel_relay/config/models.py`: new `ChannelPII.force_redact` field.
- `src/channel_relay/pii/engine.py`: `_apply_action`, `_redact_reference_rule`, and
  `redact_response_body` take a `force_redact` flag; `keyring` becomes optional on
  those paths.
- `src/channel_relay/proxy/forwarder.py`: response-side PII gate and the call into
  `redact_response_body` pass `force_redact` through and no longer hard-require a
  keyring for a force_redact channel.
- `src/channel_relay/main.py`: `build_keyring`'s `keyring_required` predicate excludes
  force_redact-only channels.
- Tests: `tests/unit/test_config.py`, `tests/unit/test_pii_engine.py`, forwarder
  integration tests, and a keyring-requirement test in main.py's test suite.
