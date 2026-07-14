# transparent-relay Specification

## Purpose
TBD - created by archiving change slice-1-mvp. Update Purpose after archive.
## Requirements
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

The relay SHALL pass through non-XML/unknown content transparently, support chunked transfer, and pass
compressed bodies through untouched when no inspection is required. When inspection is required, the
relay SHALL decode a `gzip`- or `deflate`-encoded request body **before any inspecting stage**
(operation authorization, de-anonymization, credential swap), so every inspecting stage operates on
the decoded plaintext, and SHALL re-encode the body on egress preserving the original
`Content-Encoding`. Inspection is required when PII is enabled or when configured channel credentials
require body parsing for operation parsing, request swap, or response cleanup/encryption.

Decompression SHALL be bounded by the inspectable-size cap: the relay SHALL reject with 413 when the
**decompressed** size would exceed the cap, without fully materializing an oversized body, and SHALL
not block the event loop while decompressing. A compressed body that cannot be decoded (malformed or
truncated, including a truncated-but-header-valid stream) SHALL return the `502 xml_parse_error`
contract, never an uncontrolled 500.

#### Scenario: Credential swap requires inspection
- **WHEN** a channel has credentials that require XML credential swap
- **THEN** oversized inspectable request bodies are rejected with 413 before forwarding

#### Scenario: Compressed body decoded before inspection
- **WHEN** a `Content-Encoding: gzip` (or `deflate`) request reaches an inspection-required channel
- **THEN** the body is decoded before any inspecting stage and re-encoded on egress with the same
  `Content-Encoding`

#### Scenario: Decompressed oversize rejected with 413
- **WHEN** a small compressed body would decompress to more than the inspectable-size cap on an
  inspection-required channel
- **THEN** the relay returns 413 without materializing the full decompressed body

#### Scenario: Undecodable compressed body fails to the error contract
- **WHEN** a truncated or malformed compressed body reaches an inspection-required channel
- **THEN** the relay returns 502 `xml_parse_error` (not an uncontrolled 500)

