## MODIFIED Requirements

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
