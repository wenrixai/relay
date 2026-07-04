## ADDED Requirements

### Requirement: Channel routing and forwarding
The relay SHALL route `/channel/{name}/{path}` to the resolved channel config and forward via httpx
using per-channel connect/read timeouts, with **no retries**.

#### Scenario: Request forwarded to channel
- **WHEN** a request hits `/channel/<name>/<path>` for a configured channel
- **THEN** the method, path, query, and body are forwarded to the channel's upstream base

#### Scenario: Unknown channel
- **WHEN** the `<name>` does not match a configured channel
- **THEN** the relay returns 404

#### Scenario: No retries on upstream call
- **WHEN** an upstream call fails
- **THEN** the relay does not retry the upstream request

### Requirement: Content handling and pass-through
The relay SHALL pass through non-XML/unknown content transparently, support chunked transfer, pass
compressed bodies through untouched when no inspection is required, and reject bodies exceeding the
inspectable-size cap with 413 when inspection is required.

#### Scenario: Gzip passes through untouched
- **WHEN** a gzip-encoded body is relayed and no inspection is required
- **THEN** the bytes and `Content-Encoding` are preserved unchanged

#### Scenario: Oversize inspectable body rejected
- **WHEN** a body requiring inspection exceeds the inspectable-size cap
- **THEN** the relay returns 413
