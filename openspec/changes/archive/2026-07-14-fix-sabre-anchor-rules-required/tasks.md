# Tasks — set required:true on missing Sabre passenger-name anchors

## 1. Failing tests first (TDD)

- [x] 1.1 Golden fail-closed test: `AirTicketRS` response with the name anchor's target node renamed → `redact_response` raises `RedactionError` → 502 `pii_redaction_failed`.
- [x] 1.2 Same for `DailySalesReportRS` (`sabre.sales.person_name`).
- [x] 1.3 Same for `TravelItineraryReadRS` (`sabre.itin.passenger_data`).
- [x] 1.4 Same for `GetPriceQuoteRS` (name anchor scoped to GPQ).
- [x] 1.5 Regression: normal responses for all four still redact names and forward (no false 502); `GetReservationRS` unaffected by any GPQ-scoping change.
- [x] 1.6 (Optional) a ruleset invariant test: every covered PII-heavy Sabre op has exactly one `required:true` name anchor.

## 2. Ruleset fix

- [x] 2.1 Set `required: true` on `sabre.tkt.name`, `sabre.sales.person_name`, `sabre.itin.passenger_data`.
- [x] 2.2 Give `GetPriceQuoteRS` a `required: true` passenger-name anchor — add a GPQ-scoped name rule if the shared `sabre.pq.*` rule can't carry `required:true` without forcing it on `GetReservationRS`.

## 3. Verify

- [x] 3.1 Targeted golden suites green.
- [x] 3.2 `openspec validate fix-sabre-anchor-rules-required --strict`.
- [x] 3.3 `just ci` green (coverage + fail-slow gates).
