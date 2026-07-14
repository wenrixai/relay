# observability Specification

## Purpose
TBD - created by archiving change slice-1-mvp. Update Purpose after archive.
## Requirements
### Requirement: Metrics and OTLP export
The relay SHALL record in-process OpenTelemetry metrics with OTLP export (endpoint configurable,
default Wenrix), including at least the `channels_configured` gauge and `upstream_timeouts_total`
counter, and SHALL be toggleable via configuration.

#### Scenario: channels_configured reflects config
- **WHEN** the relay starts with N configured channels
- **THEN** the `channels_configured` gauge reports N

#### Scenario: upstream_timeouts_total increments on 504
- **WHEN** a channel times out
- **THEN** `upstream_timeouts_total` for that channel increments

### Requirement: Access log
The relay SHALL emit an access log per request including `hostname`, channel-endpoint name, latency,
and `x-wenrix-trace-id`, without logging PII or bodies.

#### Scenario: Access log fields present
- **WHEN** a channel request completes
- **THEN** the access log entry contains hostname, channel-endpoint, latency, and trace id

### Requirement: PII and XML metrics
The relay SHALL record `pii_fields_redacted_total{channel, pii_type}` (fields encrypted/actioned on
responses), `pii_fields_decrypted_total{channel}` (tokens de-anonymized on requests),
`xml_parse_errors_total{channel, kind}` (hardening/parse rejections),
`channel_relay_rule_namespace_miss_total{channel}` (rule paths that resolved to a no-match because a
namespace prefix was absent from the rule's declarations), and a `rule_version` gauge reporting the
loaded `rules_version`. Metric labels SHALL never contain field values or tokens.

#### Scenario: Redaction increments counter
- **WHEN** a response redaction encrypts two `person` fields on channel `mock`
- **THEN** `pii_fields_redacted_total{channel="mock", pii_type="person"}` increases by 2

#### Scenario: De-anonymization increments counter
- **WHEN** a request containing one token is de-anonymized on channel `mock`
- **THEN** `pii_fields_decrypted_total{channel="mock"}` increases by 1

#### Scenario: Parse reject increments counter
- **WHEN** a DOCTYPE-bearing body is rejected by the hardened parser
- **THEN** `xml_parse_errors_total` increments with a `kind` label identifying the rejection

#### Scenario: Namespace no-match increments the miss counter
- **WHEN** a redaction rule path uses a namespace prefix absent from its declarations on channel
  `mock`
- **THEN** `channel_relay_rule_namespace_miss_total{channel="mock"}` increments and redaction
  continues

#### Scenario: rule_version reports loaded rules
- **WHEN** a ruleset with `rules_version: 2026-07-01` is active
- **THEN** the `rule_version` gauge/info metric reports `2026-07-01`

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

