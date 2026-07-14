# operation-authorization Specification

## Purpose
TBD - created by archiving change add-operation-authorization. Update Purpose after archive.
## Requirements
### Requirement: Operation-name allow-list enforcement
The relay SHALL enforce operation allow-lists only for channels whose `authorization.enabled` is true
and whose `authorization.allowed_operations` is non-empty. For those channels, the relay SHALL
determine the request operation from the body — using the channel handler's body-derived operation
parser, never a header (§5.3, D6) — and SHALL forward the request only if the parsed operation name
matches an entry in the list. A request whose operation is not on the list SHALL be rejected with
HTTP 403 `operation_not_allowed` before any credential injection, credential swap, or upstream call,
so a disallowed operation never reaches the channel and no credentials are applied to it.

If `authorization.enabled` is omitted or false, operation allow-list enforcement SHALL be disabled
even when `allowed_operations` contains entries.

An empty `allowed_operations` list SHALL allow all operations (no body parsing performed).

The `AllowedOperation.version` field is retained but NOT evaluated in this capability version;
enforcement is operation-name membership only.

#### Scenario: Allowed operation is forwarded
- **WHEN** a channel has `authorization.enabled=true`, restricts operations to a list, and a
  request's parsed operation is on the list
- **THEN** the relay forwards the request to the channel

#### Scenario: Disallowed operation rejected before upstream
- **WHEN** a request's parsed operation is not on the channel's non-empty allow-list
- **THEN** the relay returns 403 `operation_not_allowed` and never contacts the channel

#### Scenario: Empty list allows all
- **WHEN** a channel has `authorization.enabled=true` and `allowed_operations` is empty
- **THEN** every operation is forwarded without body parsing for authorization

#### Scenario: Disabled authorization allows all
- **WHEN** a channel omits `authorization.enabled` or sets it to false
- **THEN** every operation is forwarded without body parsing for authorization

### Requirement: Fail closed on undeterminable operation
The relay SHALL reject with 403 `operation_not_allowed` any request to a channel with
`authorization.enabled=true` and a non-empty `allowed_operations` list whose operation cannot be
determined — a body that is not inspectable XML, or does not parse — rather than forward an
unverifiable operation. The operation SHALL be parsed from the **decoded** body: a `gzip`- or
`deflate`-encoded body SHALL be decoded before the operation is determined, so a merely compressed
(but well-formed) request is authorized normally rather than treated as undeterminable. Oversize
inspectable bodies (measured after decompression) SHALL return 413, and un-parseable XML SHALL return
502 `xml_parse_error`, consistent with the other body-inspection stages.

#### Scenario: Non-XML body with a configured list
- **WHEN** a channel with a non-empty allow-list receives a request whose (decoded) body is not XML
- **THEN** the relay returns 403 `operation_not_allowed` and does not forward the request

#### Scenario: Compressed body is authorized on its decoded operation
- **WHEN** a channel with a non-empty allow-list receives a `Content-Encoding: gzip` (or `deflate`)
  request whose decoded operation is on the allow-list
- **THEN** the relay decodes the body, authorizes the operation, and forwards the request

#### Scenario: Denied operations are counted
- **WHEN** the relay rejects a request for a disallowed operation
- **THEN** it increments `channel_relay_operations_denied_total` for that channel

