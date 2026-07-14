# header-hygiene Specification

## Purpose
TBD - created by archiving change slice-1-mvp. Update Purpose after archive.
## Requirements
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

### Requirement: No Server header on responses
The relay SHALL never emit a `Server` header and SHALL strip hop-by-hop headers on the response path.
It SHALL also strip the body-framing headers `Content-Length` and `Content-Encoding`: `Content-Length`
so the serving framework recomputes it, and `Content-Encoding` because the upstream client
transparently decompresses the body the relay forwards, so the upstream encoding never describes the
served (identity) bytes and relaying it would break client decoding.

#### Scenario: Response omits Server
- **WHEN** any response is returned to the client
- **THEN** it contains no `Server` header

#### Scenario: Content-Encoding stripped from a decoded body
- **WHEN** an upstream response is `Content-Encoding: gzip` and the relay forwards the decoded body
- **THEN** the client receives the decoded body with no `Content-Encoding` header

#### Scenario: Content-Length dropped for recomputation
- **WHEN** an upstream response carries `Content-Length`
- **THEN** the relayed response omits it so the framework recomputes the length from the body

