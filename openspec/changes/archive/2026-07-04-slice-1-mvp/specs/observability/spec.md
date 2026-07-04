## ADDED Requirements

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
