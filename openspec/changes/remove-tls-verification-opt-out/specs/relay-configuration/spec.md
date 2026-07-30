## REMOVED Requirements

### Requirement: Per-channel TLS server verification opt-out
**Reason**: An unverified upstream is the exact position an attacker needs to read or rewrite
de-anonymized PII in flight, so no configuration shape justifies it. The opt-out also forced a
permanent second httpx pool plus a per-request pool-selection branch, and placed a
security-weakening switch in the customer-supplied channel document. Replaced by mandatory
verification with no configuration surface at any level.
**Migration**: Delete every channel `tls` block from configuration — `ChannelConfig` forbids unknown
fields, so a leftover block aborts startup. An upstream whose certificate does not verify must be
fixed on the certificate side (a certificate the relay's trust store accepts, or the upstream's
private CA added to that trust store); there is no replacement setting.

## ADDED Requirements

### Requirement: Upstream TLS verification is mandatory
The relay SHALL verify the upstream's TLS server certificate for every channel on every request, and
SHALL NOT expose any configuration — per-channel field or `RELAY_*` setting — that disables or relaxes
that verification. The relay SHALL use exactly one upstream connection pool and SHALL NOT select a
pool per channel. Channel configuration SHALL NOT provide any TLS verification field; a channel `tls`
block SHALL be rejected as an unknown field.

#### Scenario: Upstream certificates are always verified
- **WHEN** the relay forwards a request for any configured channel over HTTPS
- **THEN** the upstream's TLS server certificate is verified

#### Scenario: No opt-out setting exists
- **WHEN** configuration is inspected for a way to skip upstream certificate verification
- **THEN** no per-channel field and no `RELAY_*` setting provides one

#### Scenario: Single upstream client
- **WHEN** the relay forwards a request for any channel
- **THEN** it uses the one shared upstream client and no per-channel client selection occurs

#### Scenario: Channel TLS block rejected
- **WHEN** a channel config contains a `tls` block (e.g. `tls.insecure_skip_verify`)
- **THEN** config validation fails as an unknown field and startup aborts
