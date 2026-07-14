## MODIFIED Requirements

### Requirement: Required anchor rules fail closed on schema drift
Each PII-heavy Sabre operation SHALL have exactly one anchor rule (the passenger-name rule) set
`required: true`, so that if Sabre schema drift (element/attribute renames on version bumps) causes
the anchor to locate no nodes or rewrite no values, redaction fails closed (`RedactionError` → 502
`pii_redaction_failed`) rather than forwarding an unredacted response. This SHALL hold for every
covered PII-heavy operation, explicitly including `AirTicketRS`, `DailySalesReportRS`,
`TravelItineraryReadRS`, and `GetPriceQuoteRS`, not only the operations that already carry an anchor.
Where an operation is matched only by rules shared with another operation, it SHALL still have a
`required: true` name anchor scoped so the anchor applies to it.

#### Scenario: Anchor present and drift fails closed
- **WHEN** a covered operation's response no longer contains the anchor rule's target nodes
- **THEN** redaction raises and the relay returns 502 `pii_redaction_failed`, forwarding nothing

#### Scenario: Anchor matches normally
- **WHEN** the anchor rule locates and rewrites the passenger name as expected
- **THEN** redaction proceeds and the response is forwarded with names redacted

#### Scenario: Every PII-heavy operation carries an anchor
- **WHEN** the baked ruleset is inspected for `AirTicketRS`, `DailySalesReportRS`,
  `TravelItineraryReadRS`, and `GetPriceQuoteRS`
- **THEN** each has a passenger-name rule with `required: true` that applies to that operation
