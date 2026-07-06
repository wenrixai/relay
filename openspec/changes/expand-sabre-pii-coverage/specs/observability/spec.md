# observability Specification

## ADDED Requirements

### Requirement: PII coverage-gap metric
The relay SHALL record `pii_uncovered_operation_total{channel, operation}` counting PII-enabled
responses whose operation matched no redaction rules (the response is still forwarded unchanged).
Metric labels SHALL carry only the channel name and the body-derived operation name — never field
values, tokens, or other body content.

#### Scenario: Uncovered operation increments coverage metric
- **WHEN** a PII-enabled channel forwards an uncovered `PassengerDetailsRS`
- **THEN** `pii_uncovered_operation_total{channel, operation="PassengerDetailsRS"}` increases by 1

#### Scenario: Covered operation does not increment
- **WHEN** a response operation matches at least one rule
- **THEN** the coverage metric does not increment for that response

#### Scenario: Non-PII channel does not increment
- **WHEN** a channel without `pii.enabled` returns any operation
- **THEN** the coverage metric does not increment
