## MODIFIED Requirements

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
