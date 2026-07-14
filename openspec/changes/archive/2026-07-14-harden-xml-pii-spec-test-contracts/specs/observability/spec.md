## MODIFIED Requirements

### Requirement: PII and XML metrics

The relay SHALL record `pii_fields_redacted_total{channel,pii_type}`,
`pii_fields_decrypted_total{channel}`, `xml_parse_errors_total{channel,kind}`,
`channel_relay_pii_rule_path_errors_total{channel,rule_id}`, and a `rule_version` gauge reporting the
loaded `rules_version`. Metric labels SHALL never contain field values, tokens, payload fragments,
credentials, or key material. Rule-path metric labels SHALL be limited to the finite configured
channel names and active ruleset IDs.

#### Scenario: Redaction increments counter
- **WHEN** a response redaction encrypts two `person` fields on channel `mock`
- **THEN** `pii_fields_redacted_total{channel="mock",pii_type="person"}` increases by 2

#### Scenario: De-anonymization increments counter
- **WHEN** a request containing one token is de-anonymized on channel `mock`
- **THEN** `pii_fields_decrypted_total{channel="mock"}` increases by 1

#### Scenario: Parse reject increments counter
- **WHEN** a DOCTYPE-bearing body is rejected by the hardened parser
- **THEN** `xml_parse_errors_total` increments with a `kind` label identifying the rejection

#### Scenario: XPath evaluation error increments bounded counter
- **WHEN** rule `amadeus.pnr.surname` cannot evaluate its XPath for configured channel `amadeus`
- **THEN** `channel_relay_pii_rule_path_errors_total{channel="amadeus",rule_id="amadeus.pnr.surname"}`
  increases by 1

#### Scenario: rule_version reports loaded rules
- **WHEN** a ruleset with `rules_version: 2026-07-01` is active
- **THEN** the `rule_version` gauge/info metric reports `2026-07-01`
