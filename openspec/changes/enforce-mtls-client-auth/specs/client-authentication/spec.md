## MODIFIED Requirements

### Requirement: Fail closed when auth enabled without credentials

When basic auth is enabled but no username and/or password is configured, the relay SHALL abort
startup (refuse to serve) rather than serve routes without authentication. More generally, the relay
SHALL abort startup whenever **no** client-authentication mechanism is actively enforced on the served
data-plane and admin routes. Serving routes without any client authentication SHALL be possible only
when a mechanism is **explicitly disabled by configuration and no other mechanism is expected** — an
operator disabling basic auth while enabling mTLS SHALL result in enforced mTLS, never an open route.

#### Scenario: Enabled without credentials aborts startup
- **WHEN** basic auth is enabled and either the username or password is unconfigured
- **THEN** the relay aborts startup with an error and does not serve any route

#### Scenario: Enabled with credentials starts normally
- **WHEN** basic auth is enabled and both username and password are configured
- **THEN** the relay starts and enforces basic auth on served routes

#### Scenario: No mechanism enforced aborts startup
- **WHEN** basic auth is disabled and mTLS is not actively enforced (its material is unconfigured or
  its enforcement is unavailable)
- **THEN** the relay aborts startup with an error and does not serve any route open

#### Scenario: Explicitly open start requires an explicit disable of all mechanisms
- **WHEN** basic auth is explicitly disabled and mTLS is explicitly disabled by configuration
- **THEN** the relay starts and served routes require no client authentication (an operator opt-in)

## ADDED Requirements

### Requirement: mTLS client authentication is enforced when enabled
When `mtls_enabled` is true, the relay SHALL require and verify a client certificate on every served
data-plane and admin route, validating it against the configured (baked) Wenrix certificate authority.
A request without a certificate, or with a certificate that does not verify against the configured CA,
SHALL be rejected at the transport layer before reaching any route handler. The relay SHALL never
report mTLS as active (in diagnostics or otherwise) unless verification is actually wired and the
required certificate material is present. The Wenrix private key SHALL remain on Wenrix servers and is
never required by the relay.

#### Scenario: Missing client certificate rejected
- **WHEN** `mtls_enabled` is true and a request presents no client certificate
- **THEN** the connection is rejected before any route handler runs

#### Scenario: Untrusted client certificate rejected
- **WHEN** `mtls_enabled` is true and a request presents a certificate that does not verify against
  the configured CA
- **THEN** the connection is rejected before any route handler runs

#### Scenario: mTLS enabled without material aborts startup
- **WHEN** `mtls_enabled` is true but the CA/cert/key material required to enforce it is not
  configured
- **THEN** the relay aborts startup rather than serving routes with mTLS unenforced

#### Scenario: Diagnostics never over-report protection
- **WHEN** `/admin/flare` reports the client-auth state
- **THEN** it reports mTLS as active only when verification is actually enforced on served routes
