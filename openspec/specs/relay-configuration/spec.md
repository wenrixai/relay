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
