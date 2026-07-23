## ADDED Requirements

### Requirement: OTLP log export
The relay SHALL export its structured logs over OTLP to the same endpoint as metrics
(`RELAY_OTLP_ENDPOINT`), so logs, metrics, and traces reach one OTel Collector. Log export SHALL be
gated on `RELAY_TELEMETRY_LOGS_ENABLED` (default `true`) AND a configured `RELAY_OTLP_ENDPOINT`: when
either is absent the relay SHALL NOT create an OTLP log exporter. The exported logs SHALL carry the
same `Resource` identity as metrics/traces (`service.name`, `service.version`). The relay SHALL
retain its structured stderr JSON log sink in addition to OTLP export (dual sink). A Collector that
is unreachable or failing SHALL never crash the relay or block request handling. Log records SHALL
never contain request/response bodies, PII, keys, or credentials — the existing logging guarantees
are unchanged by adding the OTLP sink.

#### Scenario: Logs exported to the OTLP endpoint
- **WHEN** the relay runs with `RELAY_TELEMETRY_LOGS_ENABLED` true and `RELAY_OTLP_ENDPOINT` set
- **THEN** emitted log records are delivered to that OTLP endpoint with a Resource whose
  `service.name` is `wenrix-channel-relay` and `service.version` is the relay version

#### Scenario: No exporter without an endpoint
- **WHEN** `RELAY_TELEMETRY_LOGS_ENABLED` is true but `RELAY_OTLP_ENDPOINT` is unset
- **THEN** the relay creates no OTLP log exporter and logs go to stderr only

#### Scenario: Logs disabled
- **WHEN** `RELAY_TELEMETRY_LOGS_ENABLED` is false
- **THEN** the relay creates no OTLP log exporter regardless of the endpoint

#### Scenario: stderr sink retained alongside OTLP
- **WHEN** OTLP log export is active
- **THEN** the relay still emits its structured JSON log lines to stderr

#### Scenario: Collector failure does not crash the relay
- **WHEN** the configured OTLP endpoint is unreachable
- **THEN** the relay continues serving requests and logging to stderr, and does not crash or block
