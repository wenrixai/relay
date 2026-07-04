# error-contract Specification (delta)

## ADDED Requirements

### Requirement: PII and XML error reasons
The 502 JSON error contract SHALL be emitted with reason `pii_redaction_failed` when response
redaction fails, `pii_deanonymization_failed` when request de-anonymization fails, and
`xml_parse_error` when a body requiring inspection cannot be parsed. Each carries
`X-Wenrix-Error: <reason>`, echoes `x-wenrix-trace-id`, omits `Server`, and the `detail` field
SHALL contain no PII, tokens, or key material.

#### Scenario: Redaction failure reason
- **WHEN** PII redaction of a response fails
- **THEN** the client receives 502 JSON with reason `pii_redaction_failed` and matching
  `X-Wenrix-Error`

#### Scenario: De-anonymization failure reason
- **WHEN** de-anonymization of a request fails
- **THEN** the client receives 502 JSON with reason `pii_deanonymization_failed`

#### Scenario: XML parse failure reason
- **WHEN** an inspectable body fails hardened parsing
- **THEN** the client receives 502 JSON with reason `xml_parse_error`

#### Scenario: Detail is clean
- **WHEN** any PII/XML 502 is emitted
- **THEN** the `detail` string contains no field values, tokens, or key material
