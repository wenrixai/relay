## MODIFIED Requirements

### Requirement: Fail-closed error semantics
Any crypto, rule, or XML error during redaction or de-anonymization SHALL produce the 502 JSON error
contract (reason `pii_redaction_failed` or `pii_deanonymization_failed`) and the relay SHALL never
forward a partially processed body in either direction. Error details SHALL never contain field
values, tokens, or key material.

A rule path that fails to resolve because it uses a namespace prefix absent from its declarations is
NOT an error: it is a no-match. In that case the relay SHALL emit a dedicated warning metric
(`channel_relay_rule_namespace_miss_total`, tagged by `channel`) and a warning log, then continue
processing. This makes the "silently no redaction" case observable rather than invisible.

#### Scenario: Fail closed on crypto error
- **WHEN** a token fails to encrypt/decrypt during a redaction or de-anonymization pass for reasons
  other than a namespace no-match
- **THEN** the relay returns the 502 contract and forwards nothing

#### Scenario: Namespace no-match emits a warning metric and continues
- **WHEN** a rule path uses a namespace prefix absent from its declarations
- **THEN** the rule matches nothing, `channel_relay_rule_namespace_miss_total` increments for the
  channel, a warning is logged, and the pass continues (no 502)
