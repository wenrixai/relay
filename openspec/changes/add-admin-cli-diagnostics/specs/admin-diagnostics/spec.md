## ADDED Requirements

### Requirement: CLI-equivalent diagnostics subcommand
The relay SHALL provide a CLI subcommand that prints the same redacted diagnostics snapshot as
`GET /admin/flare`, built from the same shared snapshot builder so the two cannot diverge. The CLI
output SHALL carry the identical redaction guarantees: it SHALL NOT include raw credential values,
Basic Auth secrets, keyring material, request/response bodies, PII, or auth headers, and SHALL include
the runtime/readiness/channel summary, `rules_version`, available key-epoch ids, and telemetry state.

#### Scenario: CLI prints the redacted snapshot
- **WHEN** the operator runs the diagnostics CLI subcommand
- **THEN** it prints the redacted diagnostics snapshot (same fields as `/admin/flare`) and exits 0

#### Scenario: CLI output never leaks secrets
- **WHEN** a configured channel has credentials and a keyring is loaded
- **THEN** the CLI output includes credential key names and key-epoch ids only — never credential
  values or key material

#### Scenario: HTTP and CLI snapshots agree
- **WHEN** both `/admin/flare` and the CLI subcommand render diagnostics for the same state
- **THEN** they produce the same snapshot content from the shared builder
