## MODIFIED Requirements

### Requirement: PII configuration settings
The relay SHALL support `RELAY_PII_KEYRING` (inline JSON keyring or path handled by the keyring
capability) and `RELAY_PII_KEY_EPOCH_ACTIVE` (int, default highest epoch) as pydantic settings,
reflected in the generated JSON Schema. There SHALL be no rules-API URL setting; rules always load
from the local baked bundle. Per-channel `pii.enabled` (default false) SHALL gate all
redaction/de-anonymization behavior. Per-channel `pii.force_redact` (default false) SHALL, when
true, override every `encrypt` action outcome for that channel to the fixed literal `"REDACTED"`
instead of calling the crypto codec, for both `field` and `reference` rules; `force_redact` has no
effect when `pii.enabled` is false. Keyring values SHALL never appear in logs, error messages, or
`/admin/status`-style output.

#### Scenario: PII settings validate
- **WHEN** the settings provide a keyring and active epoch
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

### Requirement: Port and URL field validation
`RELAY_PORT` and `RELAY_TLS_PORT` SHALL be constrained to 1–65535. `proxy_pass` SHALL require an
`http://` or `https://` scheme when set. `host` SHALL be a bare hostname (no scheme, no path).
`RELAY_OTLP_ENDPOINT` remains permissive (bare `host:port` is a valid gRPC exporter form).

#### Scenario: Out-of-range port rejected
- **WHEN** `RELAY_PORT` is `0` or `65536`
- **THEN** settings validation fails at startup

#### Scenario: Scheme-less proxy_pass rejected
- **WHEN** a channel sets `proxy_pass: "webservices.example.com"`
- **THEN** validation fails; `proxy_pass: "http://mock-channel:9000"` validates
