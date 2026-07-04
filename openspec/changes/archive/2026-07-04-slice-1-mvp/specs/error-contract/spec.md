## ADDED Requirements

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
