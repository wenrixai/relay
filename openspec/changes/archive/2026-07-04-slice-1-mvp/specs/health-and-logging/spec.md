## ADDED Requirements

### Requirement: Health probes
The relay SHALL expose `/liveness` and `/readiness`. Liveness reflects process up; readiness reflects
whether config loaded and SHALL return reasons when not ready.

#### Scenario: Liveness up
- **WHEN** the process is running
- **THEN** `GET /liveness` returns 200

#### Scenario: Ready after config load
- **WHEN** config loaded successfully on startup
- **THEN** `GET /readiness` returns 200

#### Scenario: Not ready reports reasons
- **WHEN** the relay is not ready
- **THEN** `GET /readiness` returns 503 with a machine-readable list of reasons

### Requirement: Structured JSON logging
The relay SHALL emit structured JSON logs via Loguru and SHALL never log request/response bodies,
PII, keys, or credentials.

#### Scenario: Log line is JSON without body
- **WHEN** a request is logged
- **THEN** the log line is valid JSON and contains no request/response body content
