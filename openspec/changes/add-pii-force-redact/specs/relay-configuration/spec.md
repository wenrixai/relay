## MODIFIED Requirements

### Requirement: PII configuration settings
The relay SHALL support `RELAY_PII_KEYRING` (inline JSON keyring or path handled by the keyring
capability), `RELAY_PII_KEY_EPOCH_ACTIVE` (int, default highest epoch), and `RELAY_RULES_API_URL`
(rules endpoint, Wenrix default) as pydantic settings, reflected in the generated JSON Schema.
Per-channel `pii.enabled` (default false) SHALL gate all redaction/de-anonymization behavior.
Per-channel `pii.force_redact` (default false) SHALL, when true, override every `encrypt` action
outcome for that channel to the fixed literal `"REDACTED"` instead of calling the crypto codec, for
both `field` and `reference` rules; `force_redact` has no effect when `pii.enabled` is false.
Keyring values SHALL never appear in logs, error messages, or `/admin/status`-style output.

#### Scenario: PII settings validate
- **WHEN** the settings provide a keyring, active epoch, and rules URL
- **THEN** the config model validates and the values are available to the PII subsystem

#### Scenario: pii.enabled defaults off
- **WHEN** a channel config omits the `pii` block
- **THEN** the channel performs no redaction or de-anonymization

#### Scenario: force_redact defaults off
- **WHEN** a channel config sets `pii.enabled: true` and omits `force_redact`
- **THEN** `encrypt` actions for that channel produce reversible `ENC_` tokens as before

#### Scenario: force_redact overrides encryption
- **WHEN** a channel config sets `pii.enabled: true` and `pii.force_redact: true`
- **THEN** fields whose rule action is `encrypt` are replaced with the literal `"REDACTED"`
  instead of an `ENC_` token

#### Scenario: Keyring never logged
- **WHEN** config loading fails due to an invalid keyring
- **THEN** the logged error names the field and error type but never the key material
