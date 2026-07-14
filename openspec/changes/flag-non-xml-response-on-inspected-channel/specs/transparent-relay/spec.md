## ADDED Requirements

### Requirement: Inspected non-XML/MTOM response is surfaced, not silently skipped
When a channel has response inspection enabled (PII redaction or response credential swap/encryption)
and the upstream response is classified as non-XML (opaque or MTOM/XOP), the relay SHALL NOT silently
forward it unredacted: it SHALL emit the coverage metric and a warning log recording the bypass. For
an MTOM/XOP message, the relay SHALL inspect and redact the root SOAP part where feasible (binary
attachment parts remain opaque pass-through), rather than skipping the whole message. The response is
still forwarded, but the coverage gap is observable.

#### Scenario: Opaque response on an inspected channel is flagged
- **WHEN** a PII/credential-swap channel returns a response the relay classifies as opaque
- **THEN** the relay forwards it, emits the non-inspected-response metric, and logs a warning

#### Scenario: MTOM root part is inspected
- **WHEN** a PII-enabled channel returns an MTOM/XOP response whose root part is SOAP XML
- **THEN** the relay redacts the root SOAP part (attachment parts untouched) rather than skipping the
  whole response
