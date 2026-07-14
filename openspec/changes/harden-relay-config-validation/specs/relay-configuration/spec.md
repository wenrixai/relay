## MODIFIED Requirements

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

## ADDED Requirements

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
