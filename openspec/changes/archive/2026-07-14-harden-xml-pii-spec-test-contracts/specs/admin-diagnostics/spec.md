## MODIFIED Requirements

### Requirement: Redacted diagnostics snapshot

The diagnostics snapshot SHALL include runtime, readiness, channel, and in-process statistics useful
for debugging the proxy. Statistics SHALL include the total and bounded per-channel/rule totals for
PII rule-path evaluation errors under `statistics.pii_rule_path_errors_total`. The snapshot SHALL NOT
include raw credential values, Basic Auth secrets, keyring material, request or response bodies,
PII, auth headers, XPath-selected values, or tokens.

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

#### Scenario: Rule-path errors are visible without payload data
- **WHEN** an XPath evaluation error is recorded for a configured channel and active rule ID
- **THEN** `/admin/flare` includes the corresponding total in
  `statistics.pii_rule_path_errors_total` and includes no payload-derived value
