# operation-authorization Specification

## Purpose
TBD - created by archiving change add-operation-authorization. Update Purpose after archive.
## Requirements
### Requirement: Operation-name allow-list enforcement
For a channel whose `authorization.allowed_operations` is non-empty, the relay SHALL determine the
request operation from the body — using the channel handler's body-derived operation parser, never a
header (§5.3, D6) — and SHALL forward the request only if the parsed operation name matches an entry
in the list. A request whose operation is not on the list SHALL be rejected with HTTP 403
`operation_not_allowed` before any credential injection, credential swap, or upstream call, so a
disallowed operation never reaches the channel and no credentials are applied to it.

An empty `allowed_operations` list SHALL allow all operations (no body parsing performed).

The `AllowedOperation.version` field is retained but NOT evaluated in this capability version;
enforcement is operation-name membership only.

#### Scenario: Allowed operation is forwarded
- **WHEN** a channel restricts operations to a list and a request's parsed operation is on the list
- **THEN** the relay forwards the request to the channel

#### Scenario: Disallowed operation rejected before upstream
- **WHEN** a request's parsed operation is not on the channel's non-empty allow-list
- **THEN** the relay returns 403 `operation_not_allowed` and never contacts the channel

#### Scenario: Empty list allows all
- **WHEN** a channel's `allowed_operations` is empty
- **THEN** every operation is forwarded without body parsing for authorization

### Requirement: Fail closed on undeterminable operation
The relay SHALL reject with 403 `operation_not_allowed` any request to a channel with a non-empty
`allowed_operations` list whose operation cannot be determined — a body that is not inspectable XML,
or does not parse — rather than forward an unverifiable operation. Oversize inspectable bodies SHALL
return 413 and un-parseable XML SHALL return 502 `xml_parse_error`, consistent with the other
body-inspection stages.

#### Scenario: Non-XML body with a configured list
- **WHEN** a channel with a non-empty allow-list receives a request whose body is not XML
- **THEN** the relay returns 403 `operation_not_allowed` and does not forward the request

#### Scenario: Denied operations are counted
- **WHEN** the relay rejects a request for a disallowed operation
- **THEN** it increments `channel_relay_operations_denied_total` for that channel
