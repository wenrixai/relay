## ADDED Requirements

### Requirement: Env-sourced channel configuration
The relay SHALL support `RELAY_CHANNELS_JSON` as an optional pydantic setting holding the full
channel configuration document as a JSON string. When `RELAY_CHANNELS_JSON` is set (non-empty), the
relay SHALL parse and validate it against `RelayConfig` instead of reading `config_file` from disk.
When `RELAY_CHANNELS_JSON` is unset, the relay SHALL read configuration from `config_file` exactly as
today. Validation failure, error logging, and startup-abort behavior SHALL be identical between the
two sources: only the error type is logged, never the raw configuration value.

#### Scenario: Env config takes precedence over file
- **WHEN** `RELAY_CHANNELS_JSON` is set to a valid `RelayConfig`-shaped JSON document and
  `config_file` also points to an existing (different) valid file
- **THEN** the relay validates and serves the channels defined in `RELAY_CHANNELS_JSON`, and the
  file at `config_file` is not read

#### Scenario: File used when env unset
- **WHEN** `RELAY_CHANNELS_JSON` is unset or empty
- **THEN** the relay reads and validates configuration from `config_file` as before

#### Scenario: Invalid env config aborts startup
- **WHEN** `RELAY_CHANNELS_JSON` is set to a value that is not valid JSON, or is valid JSON that
  fails `RelayConfig` model validation
- **THEN** the relay logs the error type (never the raw `RELAY_CHANNELS_JSON` value) and aborts
  startup with a non-zero exit, matching file-based invalid-config behavior

#### Scenario: File-existence readiness check skipped when env is active
- **WHEN** `RELAY_CHANNELS_JSON` is set
- **THEN** the relay does not check `config_file` for existence and does not emit the "config file
  not found" readiness warning
