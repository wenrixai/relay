## ADDED Requirements

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
