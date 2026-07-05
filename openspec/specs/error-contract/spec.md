# error-contract Specification

## Purpose
TBD - created by archiving change slice-1-mvp. Update Purpose after archive.
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
