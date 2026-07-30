## REMOVED Requirements

### Requirement: Per-channel TLS server verification opt-out
**Reason**: Per-channel granularity was never used in a deployment and forced a permanent second
httpx pool plus a per-request pool-selection branch; a security-weakening switch also does not belong
in the customer-supplied channel document. Replaced by the process-wide
`RELAY_UPSTREAM_TLS_VERIFY` setting.
**Migration**: Delete every channel `tls` block from configuration — `ChannelConfig` forbids unknown
fields, so a leftover block aborts startup. To keep skipping verification, fix the upstream
certificate or move that channel to its own relay deployment with `RELAY_UPSTREAM_TLS_VERIFY=false`,
which disables verification for every channel that process serves.

## ADDED Requirements

### Requirement: Relay-wide upstream TLS verification
The relay SHALL support `RELAY_UPSTREAM_TLS_VERIFY` (`Settings.upstream_tls_verify`, default `true`)
as the single process-wide upstream TLS policy. When `true`, upstream calls for every channel SHALL
verify the upstream's TLS server certificate. When `false`, upstream calls for every channel SHALL
skip TLS server certificate verification. The relay SHALL use exactly one upstream connection pool,
built from this setting, and SHALL NOT select a pool per channel. Channel configuration SHALL NOT
provide any TLS verification field; a channel `tls` block SHALL be rejected as an unknown field.

#### Scenario: Default verifies TLS
- **WHEN** `RELAY_UPSTREAM_TLS_VERIFY` is unset
- **THEN** upstream requests for every channel verify the upstream TLS server certificate

#### Scenario: Disabled applies to all channels
- **WHEN** `RELAY_UPSTREAM_TLS_VERIFY` is `false`
- **THEN** upstream requests for every configured channel skip TLS server certificate verification

#### Scenario: Startup warns when verification is disabled
- **WHEN** `RELAY_UPSTREAM_TLS_VERIFY` is `false`
- **THEN** startup logs a WARNING stating that upstream TLS server certificate verification is
  disabled for all channels
- **AND** startup does not abort because of this setting alone

#### Scenario: Single upstream client
- **WHEN** the relay forwards a request for any channel
- **THEN** it uses the one shared upstream client and no per-channel client selection occurs

#### Scenario: Channel TLS block rejected
- **WHEN** a channel config contains a `tls` block (e.g. `tls.insecure_skip_verify`)
- **THEN** config validation fails as an unknown field and startup aborts
