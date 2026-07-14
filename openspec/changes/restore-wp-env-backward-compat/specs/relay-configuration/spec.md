## ADDED Requirements

### Requirement: WP_* legacy environment backward compatibility
The relay SHALL preserve v1 backward compatibility by reading deprecated `WP_CHANNELS_*` and
`WP_SERVER_*` environment variables at startup and synthesizing equivalent channel configuration, so a
v1 deployment driven purely by `WP_*` variables runs on v2 without a `relay.json`. Synthesized
configuration SHALL be validated by the same pydantic models as file-based configuration and SHALL be
documented as deprecated-but-functional. The precedence between `WP_*` synthesis and an explicit
`relay.json` (when both are present) SHALL be defined and documented. A representative v1 sample SHALL
drive a parity test asserting the synthesized configuration matches the intended channel set.

#### Scenario: v1 env-only deployment boots
- **WHEN** the relay starts with `WP_CHANNELS_*`/`WP_SERVER_*` set and no `relay.json`
- **THEN** it synthesizes the corresponding channels and serves them, logging their deprecation

#### Scenario: WP_* parity holds
- **WHEN** a representative v1 `WP_*` configuration is loaded
- **THEN** the synthesized channel configuration matches the expected `relay.json` equivalent

#### Scenario: Invalid synthesized config aborts
- **WHEN** `WP_*` variables synthesize a configuration that fails model validation
- **THEN** startup aborts with a sanitized error (no credential values), like file-based config
