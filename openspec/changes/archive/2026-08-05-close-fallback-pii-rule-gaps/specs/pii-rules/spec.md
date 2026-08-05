## ADDED Requirements

### Requirement: Age and IP address are classified PII
The PII rule vocabulary SHALL include `age` and `ip_address` so rules can redact those values without
misclassifying their metrics as another PII category.

#### Scenario: Age and IP rules load
- **WHEN** a ruleset contains a field rule whose `pii_type` is `age` or `ip_address`
- **THEN** strict ruleset validation accepts it and redaction counts the rewrite under that category

### Requirement: Farelogix identity-document mirrors are redacted
For `XXTransactionResponse`, the Farelogix baseline SHALL redact DOB and gender from `DOCS` SSR free
text, passenger title, identity-document issuing country, issue date, and expiry date. Typed fields
SHALL receive schema-valid sentinels, while the SSR code and operational ticket identifiers remain
unchanged.

#### Scenario: Farelogix identity data does not survive
- **WHEN** an order response carries structured document metadata and a `DOCS` SSR
- **THEN** its DOB, gender, title, issuing country, issue date, and expiry date are absent from the
  redacted response, while the `DOCS` code and `TKNE` ticket number survive

### Requirement: Travelport state is part of address redaction
For Travelport responses, state/province children under address structures SHALL be redacted with the
existing address action alongside street, city, and postal code.

#### Scenario: Travelport state redacted
- **WHEN** a Travelport booking address contains a `State` value
- **THEN** the value is redacted and the country and operational record identifiers remain unchanged
