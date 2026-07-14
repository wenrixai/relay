# error-contract Specification

## Purpose
Define stable, sanitized client-facing error responses and upstream failure mappings.
## Requirements
### Requirement: Upstream timeout error
On a channel connect/read timeout the relay SHALL return HTTP 504 with `Content-Type: text/html`, a
short HTML notice, and header `X-Wenrix-Error: upstream_timeout`, and SHALL omit `Server`.

#### Scenario: Timeout returns 504
- **WHEN** a channel exceeds its connect or read timeout
- **THEN** the relay returns 504 text/html with `X-Wenrix-Error: upstream_timeout`

### Requirement: Internal and oversize errors
On internal errors the relay SHALL return HTTP 502 `application/json`
`{error, reason, detail, trace_id}` with `X-Wenrix-Error: <reason>`; oversize inspectable bodies
SHALL return 413. All error responses omit `Server`.

#### Scenario: Internal error returns 502 JSON
- **WHEN** the relay encounters an internal error
- **THEN** it returns 502 JSON with `error`, `reason`, `detail`, `trace_id` and `X-Wenrix-Error`

#### Scenario: trace_id echoes request trace id
- **WHEN** the request carries `x-wenrix-trace-id`
- **THEN** the 502 body `trace_id` equals that value

### Requirement: PII and XML error reasons

The 502 JSON error contract SHALL be emitted with reason `pii_redaction_failed` when response
redaction fails, `pii_deanonymization_failed` when request de-anonymization fails,
`xml_parse_error` when a body requiring inspection cannot be parsed, and
`credential_swap_failed` when configured structural credential swap cannot be completed. Each
carries `X-Wenrix-Error: <reason>`, echoes `x-wenrix-trace-id`, omits `Server`, and the `detail`
field SHALL contain no PII, tokens, credentials, or key material.

#### Scenario: Credential swap failure reason
- **WHEN** configured credential swap cannot locate or parse a required credential target
- **THEN** the client receives 502 JSON with reason `credential_swap_failed`

### Requirement: Operation-not-allowed error
When a request's operation is not permitted for a channel (operation authorization), the relay SHALL
return HTTP 403 `application/json` `{error:"forbidden", reason:"operation_not_allowed", detail,
trace_id}` with header `X-Wenrix-Error: operation_not_allowed`. The response SHALL echo
`x-wenrix-trace-id`, omit `Server`, and its `detail` SHALL contain no PII, tokens, credentials, or
key material.

#### Scenario: Disallowed operation returns 403 JSON
- **WHEN** operation authorization rejects a request
- **THEN** the client receives 403 JSON with reason `operation_not_allowed` and
  `X-Wenrix-Error: operation_not_allowed`

#### Scenario: trace_id echoes request trace id
- **WHEN** the rejected request carries `x-wenrix-trace-id`
- **THEN** the 403 body `trace_id` equals that value
