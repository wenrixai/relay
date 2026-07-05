# admin-diagnostics Specification

## Purpose
TBD - created by archiving change add-admin-diagnostics-route. Update Purpose after archive.
## Requirements
### Requirement: Authenticated admin diagnostics

The relay SHALL expose `GET /admin/flare` as an admin diagnostics JSON snapshot. The route SHALL
require valid Basic Auth credentials and SHALL fail closed with `401` when Basic Auth is disabled or
credentials are incomplete. Health probes SHALL remain unauthenticated.

#### Scenario: Missing admin credentials rejected
- **WHEN** a request to `/admin/flare` omits Basic Auth credentials
- **THEN** the relay returns `401` with a `WWW-Authenticate: Basic` header

#### Scenario: Admin auth fails closed when disabled
- **WHEN** Basic Auth is disabled or missing configured credentials
- **THEN** `/admin/flare` returns `401`

#### Scenario: Valid admin credentials return diagnostics
- **WHEN** a request to `/admin/flare` presents valid Basic Auth credentials
- **THEN** the relay returns a JSON diagnostics snapshot

### Requirement: Redacted diagnostics snapshot

The diagnostics snapshot SHALL include runtime, readiness, channel, and in-process statistics useful
for debugging the proxy. It SHALL NOT include raw credential values, Basic Auth secrets, keyring
material, request or response bodies, PII, or auth headers.

#### Scenario: Channel configuration is summarized safely
- **WHEN** a configured channel has credentials
- **THEN** the diagnostics snapshot includes the credential key names and credential count
- **AND** it does not include credential values

#### Scenario: Sensitive settings are presence-only
- **WHEN** settings include auth, rules, telemetry, and keyring configuration
- **THEN** the diagnostics snapshot reports configured booleans and safe scalar values only

#### Scenario: Statistics reflect in-process counters
- **WHEN** relay metric methods record timeout, PII, and XML events
- **THEN** the diagnostics snapshot includes the current in-process counter totals
