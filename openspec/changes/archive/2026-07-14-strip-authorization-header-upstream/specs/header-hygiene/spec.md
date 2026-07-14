## MODIFIED Requirements

### Requirement: Header hygiene toward the channel
The relay SHALL strip hop-by-hop headers (`Connection`, `Keep-Alive`, `Proxy-Authenticate`,
`Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`, and every token listed in the
inbound `Connection` header), forwarding/identity headers (`X-Forwarded-*`, `X-Real-IP`, `Forwarded`,
`Via`), the client `Authorization` header, all `x-wenrix-*`, and all `Proxy-*` before forwarding, and
SHALL rewrite `Host` (and SNI) to the channel host. The relay SHALL NOT add `Via`, `Forwarded`, or
`X-Forwarded-*`.

The client `Authorization` header authenticates the client to the relay and SHALL NEVER be forwarded
to a channel. An outbound `Authorization` header SHALL reach a channel only when a credential-swap
handler sets it explicitly (e.g. Travelport HTTP Basic auth), and that value SHALL be the channel's
own credential, never the client's.

#### Scenario: Clean upstream request
- **WHEN** a request carrying hop-by-hop, forwarding, `Authorization`, `x-wenrix-*`, and `Proxy-*`
  headers is relayed
- **THEN** none of those headers reach the channel and `Host` is the channel host

#### Scenario: Client Authorization never leaks to a pass-through channel
- **WHEN** a request with a client `Authorization: Basic …` header is relayed to a channel with no
  credential swap configured
- **THEN** the forwarded upstream request carries no `Authorization` header

#### Scenario: Credential-swap handler may set its own Authorization
- **WHEN** a credential-swap handler (e.g. Travelport) sets an outbound `Authorization` header during
  the swap
- **THEN** the channel receives that handler-set value, not the client's `Authorization`
