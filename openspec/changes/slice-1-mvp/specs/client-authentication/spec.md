## ADDED Requirements

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
