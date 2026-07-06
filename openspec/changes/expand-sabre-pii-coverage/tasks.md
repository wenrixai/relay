## 1. Engine coverage outcome (redaction-engine)

- [x] 1.1 Write failing tests: `redact_response_body` reports (a) covered=True when ≥1 rule matches even with zero rewrites, (b) covered=False + parsed operation when no rule matches
- [x] 1.2 Extend `redact_response_body` to return the coverage outcome (covered flag + operation) alongside body+counts; compute from the existing `_select_rules_for_channels` result
- [x] 1.3 Update all existing callers/tests for the new return shape
- [x] 1.4 Green: engine unit tests pass, existing redaction tests still pass; uncovered op still returns body unchanged (no error)

## 2. Coverage metric (observability)

- [x] 2.1 Write failing test: `record_uncovered_operation(channel, operation)` increments `pii_uncovered_operation_total{channel, operation}` and appears in totals
- [x] 2.2 Add the counter instrument + `record_uncovered_operation` to `RelayMetrics`, extend `_MetricTotals`
- [x] 2.3 Satisfy pylint (attribute count) as done for prior counters; green

## 3. Forwarder emits metric (observability)

- [x] 3.1 Write failing tests: PII-enabled uncovered response → forwarded unchanged AND `pii_uncovered_operation_total` increments; covered op → no increment; non-PII channel → no increment
- [x] 3.2 In `_response_pii_stage`, when the engine coverage outcome is uncovered, call `record_uncovered_operation` and forward unchanged (no error, no config)
- [x] 3.3 Green: forwarder tests pass

## 4. Sabre baseline rules (sabre-pii-baseline)

- [ ] 4.1 Add sanitized fixtures under `tests/fixtures/sabre/` for each new operation, sourced from `src/tests/resources/sources/sabre` and Wenrix parsing models
- [ ] 4.2 Author `field`/`reference` rules in `rules_fallback.json` for `CreatePassengerNameRecordRS`, `PassengerDetailsRS`, `TravelItineraryHistoryRS`, `GetTicketingDocumentRS`, `GetETicketDetailsRS`, `GetTicketInformationFromAirlineRS`, `TicketRefundRS`, `TicketExchangeRS`, `DailyRefundReportRS`, `PastDatePnrDetailsRS`, `QueueAccessRS` (XPaths + explicit namespaces per Wenrix models; use `channel-implementation` skill)
- [ ] 4.3 Set `required: true` on the passenger-name anchor rule of each PII-heavy operation (incl. existing `GetReservationRS`)
- [ ] 4.4 Write golden unit tests per new operation: counts, reversibility, one-way masks, non-PII preservation, `required` drift fails closed
- [ ] 4.5 Green: Sabre golden unit suite passes

## 5. Integration + CI

- [ ] 5.1 Relay integration tests: full pipeline for a representative new operation (credential swap ordering + `BinarySecurityToken` encryption + PII redaction) and the uncovered-operation metric end-to-end
- [ ] 5.2 `just ci` green (lint, fmt, types, pylint, tests); coverage gate met
- [ ] 5.3 `openspec validate expand-sabre-pii-coverage --strict` passes
