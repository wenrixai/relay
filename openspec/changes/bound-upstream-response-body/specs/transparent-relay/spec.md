## MODIFIED Requirements

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

The same bound SHALL apply to the **upstream response** body, since the channel is a semi-untrusted
party. For a channel that inspects the response (PII redaction or response credential swap/encryption),
the relay SHALL reject an upstream response whose decoded size exceeds the inspectable-size cap before
buffering/parsing it, and SHALL enforce a ceiling on the buffered response even for pass-through
channels so a compressed upstream bomb cannot exhaust process memory. The relay SHALL NOT fully
materialize an oversized decompressed upstream body.

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

#### Scenario: Oversize upstream response is rejected, not buffered unbounded
- **WHEN** an inspected channel returns a response whose decoded size exceeds the inspectable-size cap
  (including a small compressed body that inflates past the cap)
- **THEN** the relay rejects it with the defined error before fully buffering, rather than OOMing

#### Scenario: Compressed upstream bomb cannot exhaust memory on pass-through
- **WHEN** any channel returns a small compressed body that would inflate beyond the response ceiling
- **THEN** the relay stops at the ceiling rather than materializing the full decompressed body
