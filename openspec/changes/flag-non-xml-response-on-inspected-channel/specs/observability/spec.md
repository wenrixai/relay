## ADDED Requirements

### Requirement: Non-inspected-response coverage metric
The relay SHALL record a metric (`channel_relay_response_not_inspected_total`, tagged by `channel` and
a coarse `kind` such as `mtom`/`opaque`) counting responses on a channel with response inspection
enabled (PII redaction or response credential swap/encryption) that were **not** inspected because the
relay classified the response as non-XML. Labels SHALL carry only the channel name and the coarse kind
— never body content. This makes an upstream suppressing redaction by mislabeling its `Content-Type`
observable instead of silent.

#### Scenario: Non-XML response on a PII channel increments the metric
- **WHEN** a PII-enabled channel returns a response classified as `opaque` or `mtom`
- **THEN** `channel_relay_response_not_inspected_total{channel, kind}` increments and a warning is
  logged

#### Scenario: XML response does not increment
- **WHEN** an inspected channel returns an XML response that is redacted normally
- **THEN** the non-inspected-response metric does not increment
