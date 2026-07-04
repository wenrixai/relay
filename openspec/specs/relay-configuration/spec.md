# relay-configuration Specification

## Purpose
TBD - created by archiving change slice-1-mvp. Update Purpose after archive.
## Requirements
### Requirement: Pydantic-first configuration
The relay SHALL express all configuration as pydantic v2 models as the single source of truth, and
SHALL generate the JSON Schema from those models (never hand-maintained).

#### Scenario: Minimal channel applies type defaults
- **WHEN** a channel config provides only `name` and `type`
- **THEN** the model validates and resolves the per-type default `host` and a `proxy_pass` of
  `https://<host>`

#### Scenario: Generated JSON Schema marks name and type required
- **WHEN** the JSON Schema is generated from the channel model
- **THEN** `name` and `type` are listed as required properties

#### Scenario: Unknown channel type rejected
- **WHEN** a channel config sets `type` to a value outside the supported enum
- **THEN** validation fails

### Requirement: Startup aborts on invalid config
The relay SHALL log the validation error and abort startup with a non-zero exit when configuration is
invalid.

#### Scenario: Invalid config aborts
- **WHEN** the configured JSON config file fails model validation
- **THEN** the loader raises and startup does not complete

### Requirement: PII configuration settings
The relay SHALL support `RELAY_PII_KEYRING` (inline JSON keyring or path handled by the keyring
capability), `RELAY_PII_KEY_EPOCH_ACTIVE` (int, default highest epoch), and `RELAY_RULES_API_URL`
(rules endpoint, Wenrix default) as pydantic settings, reflected in the generated JSON Schema.
Per-channel `pii.enabled` (default false) SHALL gate all redaction/de-anonymization behavior.
Keyring values SHALL never appear in logs, error messages, or `/admin/status`-style output.

#### Scenario: PII settings validate
- **WHEN** the settings provide a keyring, active epoch, and rules URL
- **THEN** the config model validates and the values are available to the PII subsystem

#### Scenario: pii.enabled defaults off
- **WHEN** a channel config omits the `pii` block
- **THEN** the channel performs no redaction or de-anonymization

#### Scenario: Keyring never logged
- **WHEN** config loading fails due to an invalid keyring
- **THEN** the logged error names the field and error type but never the key material
