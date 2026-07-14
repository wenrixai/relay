## MODIFIED Requirements

### Requirement: PII coverage-gap metric
The relay SHALL record `pii_uncovered_operation_total{channel, operation}` counting PII-enabled
responses whose operation matched no redaction rules (the response is still forwarded unchanged).
Metric labels SHALL carry only the channel name and the body-derived operation name — never field
values, tokens, or other body content.

Because the `operation` value is derived from the untrusted upstream response, the relay SHALL bound
the distinct `operation` values it retains per channel (for both the exported metric's label
cardinality and any in-process totals): a cap on retained keys with an overflow bucket, or dropping
the `operation` dimension entirely. An upstream returning endlessly varied element names SHALL NOT
cause unbounded in-process memory growth or unbounded metric cardinality, and the admin diagnostics
snapshot SHALL reflect only the bounded set.

#### Scenario: Uncovered operation increments coverage metric
- **WHEN** a PII-enabled channel forwards an uncovered `PassengerDetailsRS`
- **THEN** `pii_uncovered_operation_total{channel, operation="PassengerDetailsRS"}` increases by 1

#### Scenario: Covered operation does not increment
- **WHEN** a response operation matches at least one rule
- **THEN** the coverage metric does not increment for that response

#### Scenario: Non-PII channel does not increment
- **WHEN** a channel without `pii.enabled` returns any operation
- **THEN** the coverage metric does not increment

#### Scenario: Distinct-operation cardinality is bounded
- **WHEN** an upstream returns many responses with distinct, never-covered operation names on one
  channel
- **THEN** the retained per-channel set (and the admin snapshot) stays within a fixed bound rather
  than growing without limit
