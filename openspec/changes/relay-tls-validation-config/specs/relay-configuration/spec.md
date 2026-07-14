## ADDED Requirements

### Requirement: Per-channel TLS server verification opt-out
The relay SHALL support a per-channel `tls.insecure_skip_verify` boolean (default `false`). When
`false` (the default, or when the `tls` block is omitted), upstream calls for that channel SHALL
verify the upstream's TLS server certificate as normal. When `true`, upstream calls for that channel
only SHALL skip TLS server certificate verification; every other channel configured in the same relay
process SHALL continue to verify its own upstream's certificate, unaffected by this setting on
another channel.

#### Scenario: Default verifies TLS
- **WHEN** a channel config omits the `tls` block
- **THEN** upstream requests for that channel verify the upstream TLS server certificate

#### Scenario: Explicit opt-out skips verification for that channel only
- **WHEN** a channel config sets `tls.insecure_skip_verify: true`
- **THEN** upstream requests for that channel do not verify the upstream TLS server certificate
- **AND** upstream requests for every other configured channel still verify their own certificates

#### Scenario: Startup warns on insecure TLS channels
- **WHEN** one or more channels set `tls.insecure_skip_verify: true`
- **THEN** startup logs a WARNING naming each such channel and stating that TLS server
  verification is disabled for it
- **AND** startup does not abort because of this setting alone
