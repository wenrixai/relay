## MODIFIED Requirements

### Requirement: Fail-closed error semantics
Any crypto, rule, or XML error during redaction or de-anonymization SHALL produce the 502 JSON
error contract (reason `pii_redaction_failed` or `pii_deanonymization_failed`) and the relay SHALL
never forward a partially processed body in either direction. Error details SHALL never contain
PII or key material.

A rule path that fails to resolve because it uses a namespace prefix absent from its declarations is
NOT such an error: it is a no-match. In that case the relay SHALL emit a dedicated warning metric
(`channel_relay_rule_namespace_miss_total`, tagged by `channel`) and continue processing, so the
"silently no redaction" case is observable rather than invisible.

#### Scenario: Redaction failure drops response
- **WHEN** encryption of a located field fails mid-document
- **THEN** the client receives 502 `pii_redaction_failed` and none of the upstream body

#### Scenario: Bad token blocks request
- **WHEN** a request token fails decoding or decryption
- **THEN** the channel receives nothing and the client gets 502 `pii_deanonymization_failed`

#### Scenario: Namespace no-match emits a warning metric and continues
- **WHEN** a rule path uses a namespace prefix absent from its declarations
- **THEN** the rule matches nothing, `channel_relay_rule_namespace_miss_total` increments for the
  channel, and the pass continues (no 502)
