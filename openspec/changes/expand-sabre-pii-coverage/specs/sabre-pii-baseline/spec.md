# sabre-pii-baseline Specification

## MODIFIED Requirements

### Requirement: Sabre operations covered by the baked ruleset
The baked ruleset (`rules_fallback.json`) SHALL contain field rules for channel `sabre` selected by
body-derived operation, covering the original baseline (`GetReservationRS`, `TravelItineraryReadRS`,
`GetPriceQuoteRS` — plain and PQR variants share one operation name, `AirTicketRS`,
`DailySalesReportRS`) plus the high-priority PII-bearing operations used by Wenrix handlers:
`CreatePassengerNameRecordRS`, `PassengerDetailsRS`, `TravelItineraryHistoryRS`,
`GetTicketingDocumentRS`, `GetETicketDetailsRS`, `GetTicketInformationFromAirlineRS`,
`TicketRefundRS`, `TicketExchangeRS`, `DailyRefundReportRS`, `PastDatePnrDetailsRS`, and
`QueueAccessRS`. XPaths SHALL be sourced from the Wenrix parsing models
(`sources/itinerary.py`, `ticketing.py`, `pnr.py`, `history.py`, `queue.py`, `sales_report.py`),
which enumerate the elements/attributes carrying names, contact details, documents, and payment data.
Rules SHALL bind every namespace they use explicitly (Sabre payloads use default namespaces — each
rule declares its own prefix→URI map).

#### Scenario: Rules select per operation
- **WHEN** a Sabre response body's SOAP Body first-child local-name is one of the covered operations
- **THEN** only that operation's rules (plus shared-pattern rules whose operation regex matches) apply

#### Scenario: Newly covered operation redacts names
- **WHEN** a `PassengerDetailsRS` or `CreatePassengerNameRecordRS` response echoes passenger names
- **THEN** those names are redacted per the rule's action and no plaintext name is forwarded

#### Scenario: Uncovered operation forwarded with coverage metric
- **WHEN** a Sabre response carries an operation with no baseline rules
- **THEN** the relay forwards the body unchanged and emits `pii_uncovered_operation_total{channel,
  operation}` so the gap is discoverable

### Requirement: Golden coverage from sanitized fixtures
Sanitized fixtures for each covered operation (original and newly added) SHALL live in
`tests/fixtures/sabre/` and drive golden unit tests (rule-level: counts, reversibility, one-way masks,
non-PII preservation) plus relay integration tests (full pipeline: credential swap ordering,
`BinarySecurityToken` encryption via the existing `SabreHandler`, PII redaction). All tests finish
within the configured pytest timeout with no network.

#### Scenario: Golden suite green
- **WHEN** the Sabre golden unit and integration suites run against the baked ruleset
- **THEN** every covered operation redacts per its rules and encrypted fields round-trip

#### Scenario: New-operation fixtures present
- **WHEN** a newly covered operation is added to the baseline
- **THEN** a sanitized fixture for it exists under `tests/fixtures/sabre/` and drives a golden test

## ADDED Requirements

### Requirement: Required anchor rules fail closed on schema drift
Each PII-heavy Sabre operation SHALL have one anchor rule (the passenger-name rule) set
`required: true`, so that if Sabre schema drift (element/attribute renames on version bumps) causes
the anchor to locate no nodes or rewrite no values, redaction fails closed (`RedactionError` → 502
`pii_redaction_failed`) rather than forwarding an unredacted response.

#### Scenario: Anchor present and drift fails closed
- **WHEN** a covered operation's response no longer contains the anchor rule's target nodes
- **THEN** redaction raises and the relay returns 502 `pii_redaction_failed`, forwarding nothing

#### Scenario: Anchor matches normally
- **WHEN** the anchor rule locates and rewrites the passenger name as expected
- **THEN** redaction proceeds and the response is forwarded with names redacted
