# relay-configuration Specification

## Purpose
TBD - created by archiving change slice-1-mvp. Update Purpose after archive.
## Requirements
### Requirement: Pydantic-first configuration

The relay SHALL express all configuration as pydantic v2 models as the single source of truth, and
SHALL generate the JSON Schema from those models (never hand-maintained). Per-channel `credentials`
SHALL be a string map whose keys are interpreted by the selected channel handler. Empty credentials
SHALL be valid and SHALL disable credential swap.

#### Scenario: Credential map accepted
- **WHEN** a channel config provides credential keys for its channel type
- **THEN** the model validates and the handler can read those values during forwarding

### Requirement: Startup aborts on invalid config
The relay SHALL log the validation error and abort startup with a non-zero exit when configuration is
invalid. A configuration is invalid — and startup SHALL abort — when any configured channel resolves
to no upstream base: that is, when `proxy_pass` remains unset after per-type `host` defaulting (a
channel type with no default host that supplies neither `host` nor `proxy_pass`). The relay SHALL NOT
report such a channel as ready and then fail every request at forward time.

#### Scenario: Invalid config aborts
- **WHEN** the configured JSON config file fails model validation
- **THEN** the loader raises and startup does not complete

#### Scenario: Channel with no resolvable upstream aborts startup
- **WHEN** a channel of a type with no default host is configured without `host` or `proxy_pass`
- **THEN** startup aborts with an error naming the channel, rather than the relay booting ready and
  returning an internal error on every request to that channel

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

