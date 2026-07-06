## MODIFIED Requirements

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
