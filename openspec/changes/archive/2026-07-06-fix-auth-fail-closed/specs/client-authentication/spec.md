## ADDED Requirements

### Requirement: Fail closed when auth enabled without credentials

When basic auth is enabled but no username and/or password is configured, the relay SHALL
abort startup (refuse to serve) rather than serve routes without authentication. Serving
routes without credentials SHALL be possible only when basic auth is explicitly disabled by
configuration.

#### Scenario: Enabled without credentials aborts startup
- **WHEN** basic auth is enabled and either the username or password is unconfigured
- **THEN** the relay aborts startup with an error and does not serve any route

#### Scenario: Enabled with credentials starts normally
- **WHEN** basic auth is enabled and both username and password are configured
- **THEN** the relay starts and enforces basic auth on served routes

#### Scenario: Explicitly disabled starts open
- **WHEN** basic auth is explicitly disabled by configuration
- **THEN** the relay starts and served routes require no credentials
