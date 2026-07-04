## ADDED Requirements

### Requirement: Header hygiene toward the channel
The relay SHALL strip hop-by-hop headers (`Connection`, `Keep-Alive`, `Proxy-Authenticate`,
`Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`, and every token listed in the
inbound `Connection` header), forwarding/identity headers (`X-Forwarded-*`, `X-Real-IP`, `Forwarded`,
`Via`), all `x-wenrix-*`, and all `Proxy-*` before forwarding, and SHALL rewrite `Host` (and SNI) to
the channel host. The relay SHALL NOT add `Via`, `Forwarded`, or `X-Forwarded-*`.

#### Scenario: Clean upstream request
- **WHEN** a request carrying hop-by-hop, forwarding, `x-wenrix-*`, and `Proxy-*` headers is relayed
- **THEN** none of those headers reach the channel and `Host` is the channel host

### Requirement: No Server header on responses
The relay SHALL never emit a `Server` header and SHALL strip hop-by-hop headers on the response path.

#### Scenario: Response omits Server
- **WHEN** any response is returned to the client
- **THEN** it contains no `Server` header
