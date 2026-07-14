# client-authentication Specification

## Purpose
Define client authentication, startup validation, and health-route access boundaries.
## Requirements
### Requirement: Default HTTP basic auth
The relay SHALL enforce HTTP basic auth on served channel and admin routes by default, using
constant-time credential comparison, and SHALL be toggleable via configuration. Health probes SHALL
remain unauthenticated.

#### Scenario: Missing credentials rejected
- **WHEN** a request to a served route omits credentials and auth is enabled
- **THEN** the relay returns 401 with a `WWW-Authenticate: Basic` header

#### Scenario: Valid credentials pass
- **WHEN** a request presents valid credentials and auth is enabled
- **THEN** the request proceeds

#### Scenario: Probes stay open
- **WHEN** auth is enabled
- **THEN** `/liveness` and `/readiness` are reachable without credentials

#### Scenario: Auth disabled
- **WHEN** basic auth is disabled by config
- **THEN** served routes require no credentials

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
