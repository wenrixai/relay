# Tasks — surface non-XML responses on inspected channels

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_forwarder.py`: a PII/credential-swap channel returning SOAP under `application/octet-stream` (opaque) → forwarded, `channel_relay_response_not_inspected_total{channel, kind="opaque"}` increments, warning logged.
- [ ] 1.2 Same for an MTOM (`multipart/related`/`xop+xml`) response.
- [ ] 1.3 MTOM root-part redaction: the SOAP root part's PII is redacted while attachment parts are untouched.
- [ ] 1.4 An XML response on the same channel does NOT increment the metric.

## 2. Implementation

- [ ] 2.1 `metrics.py`: define `channel_relay_response_not_inspected_total{channel, kind}` + a record method.
- [ ] 2.2 `forwarder.py`: when a redaction/credential-swap channel's `response_kind` is non-XML, emit the metric + log before forwarding.
- [ ] 2.3 Route MTOM to root-part extraction (parse the root SOAP part, inspect it, leave binary parts opaque) where feasible.

## 3. Verify

- [ ] 3.1 Targeted suites green.
- [ ] 3.2 `openspec validate flag-non-xml-response-on-inspected-channel --strict`.
- [ ] 3.3 `just ci` green.
