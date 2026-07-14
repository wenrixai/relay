# relay-configuration Specification

## Purpose
Define validated process and channel configuration, defaults, and fail-closed startup behavior.
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
invalid. The raised error and every log line it produces SHALL identify failing fields by path and
error type only, and SHALL NEVER contain configuration values (including per-channel `credentials`
values), regardless of which logger ultimately renders the exception. The sanitized error SHALL NOT
chain to the original validation error.

#### Scenario: Invalid config aborts
- **WHEN** the configured JSON config file fails model validation
- **THEN** the loader raises a sanitized configuration error and startup does not complete

#### Scenario: Credential values never leak into the abort error
- **WHEN** a channel's `credentials` block fails validation (e.g. a non-string value)
- **THEN** the raised error's message and cause chain contain the field path and error type but no
  credential value

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

### Requirement: Channel names are unique
`RelayConfig` SHALL reject configurations containing two channels with the same `name`, naming the
duplicate in the validation error.

#### Scenario: Duplicate channel name rejected
- **WHEN** two channels share the name `"tf"`
- **THEN** validation fails and the error names `"tf"`

### Requirement: Port and URL field validation
`RELAY_PORT` and `RELAY_TLS_PORT` SHALL be constrained to 1–65535. `proxy_pass` and
`RELAY_RULES_API_URL` SHALL require an `http://` or `https://` scheme when set. `host` SHALL be a
bare hostname (no scheme, no path). `RELAY_OTLP_ENDPOINT` remains permissive (bare `host:port` is a
valid gRPC exporter form).

#### Scenario: Out-of-range port rejected
- **WHEN** `RELAY_PORT` is `0` or `65536`
- **THEN** settings validation fails at startup

#### Scenario: Scheme-less proxy_pass rejected
- **WHEN** a channel sets `proxy_pass: "webservices.example.com"`
- **THEN** validation fails; `proxy_pass: "http://mock-channel:9000"` validates

### Requirement: Unenforced external authorization warns at startup
`authorization.external` is accepted by the model but is NOT enforced by the request pipeline in
this version. The relay SHALL emit a WARNING log at startup for every channel that configures
`authorization.external`, stating that it is not enforced.

#### Scenario: Warning on configured external authorization
- **WHEN** a channel config sets `authorization.external.url`
- **THEN** startup logs a WARNING naming the channel and stating external authorization is not
  enforced
