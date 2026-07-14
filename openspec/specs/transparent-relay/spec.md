# transparent-relay Specification

## Purpose
Define channel routing, transparent forwarding, content handling, and retry behavior.
## Requirements
### Requirement: Channel routing and forwarding

The relay SHALL route both `/channel/{name}` and `/channel/{name}/{path}` to the resolved channel
config and forward via httpx using per-channel connect/read timeouts, with **no request-level
retries**: a request that has reached the upstream (i.e. any bytes sent) is never resent. The relay
MAY retry a failed connection *attempt* (TCP/TLS connect, before any request bytes are sent) up to a
configured bound, since no upstream side effect can have occurred yet. The bare route is the
empty-path compatibility form and follows the same processing and security pipeline.

#### Scenario: Request forwarded to channel
- **WHEN** a request hits `/channel/<name>/<path>` for a configured channel
- **THEN** the method, path, query, and body are forwarded to the channel's upstream base

#### Scenario: Bare route forwarded to channel root
- **WHEN** a request hits `/channel/<name>` for a configured channel
- **THEN** it is forwarded to the channel's upstream base path through the same pipeline

#### Scenario: Unknown channel
- **WHEN** the `<name>` does not match a configured channel
- **THEN** the relay returns 404

#### Scenario: No retry once a request reached the upstream
- **WHEN** an upstream call fails after the request was sent (timeout, reset, non-2xx, or any
  failure past connection establishment)
- **THEN** the relay does not retry the request

#### Scenario: Connection-attempt retry is safe
- **WHEN** the relay cannot establish a connection to the channel's upstream (connect refused or
  connect timeout, before any request bytes are sent)
- **THEN** the shared client may retry the connection attempt up to the configured bound, and only
  one HTTP request is ever sent to the channel for that call

### Requirement: Content handling and pass-through

The relay SHALL inspect only XML/SOAP bodies. It SHALL support inspected XML sent directly or with
`Content-Encoding: gzip`, support chunked transfer, pass bodies through byte-equivalently when no
configured stage requires body inspection, and reject bodies exceeding the inspectable-size cap
with 413 when inspection is required. Inspection is required when PII is enabled or configured
channel credentials require structural body parsing for request swap, response cleanup, or response
auth encryption. JSON, MTOM/multipart, deflate-encoded, and unknown content are unsupported when
inspection is required.

Unsupported request content that requires inspection SHALL fail before forwarding with HTTP 415 and
reason `unsupported_content_type`. Unsupported upstream response content that requires inspection
SHALL fail with HTTP 502 and the same reason, and none of the upstream body SHALL be returned.
Operation authorization retains its separately specified non-XML behavior.

#### Scenario: Credential swap requires inspection
- **WHEN** a channel has credentials that require structural XML credential swap
- **THEN** oversized inspectable request bodies are rejected with 413 before forwarding

#### Scenario: Opaque content passes through when inspection is disabled
- **WHEN** neither request nor response configuration requires body inspection
- **THEN** non-XML and compressed bodies pass through without structural parsing

#### Scenario: Unsupported request inspection fails closed
- **WHEN** a request is JSON, MTOM/multipart, deflate-encoded, or unknown and configured PII or
  structural credential handling requires body inspection
- **THEN** the relay returns 415 `unsupported_content_type` and makes no upstream request

#### Scenario: Unsupported response inspection fails closed
- **WHEN** an upstream response is JSON, MTOM/multipart, deflate-encoded, or unknown and configured
  PII or structural credential cleanup requires body inspection
- **THEN** the relay returns 502 `unsupported_content_type` and none of the upstream body

#### Scenario: Gzip XML inspection succeeds
- **WHEN** an XML body requiring inspection is encoded with gzip
- **THEN** the relay decodes it, applies the configured structural stages, and preserves the
  appropriate wire encoding toward the next hop
