# Set required:true on missing Sabre passenger-name anchors

## Why

The `sabre-pii-baseline` spec requires that *"each PII-heavy Sabre operation SHALL have one anchor
rule (the passenger-name rule) set `required: true`"* so schema drift fails closed
(`RedactionError` → 502) instead of forwarding an unredacted response. The baked `rules_fallback.json`
violates this for several operations — their passenger-name rule is `required: false`:

- `sabre.tkt.name` (`AirTicketRS`)
- `sabre.sales.person_name` (`DailySalesReportRS`)
- `sabre.itin.passenger_data` (`TravelItineraryReadRS`)
- `GetPriceQuoteRS` — matched only by shared `sabre.pq.*` rules, all `required: false` (no name anchor)

For these operations, a Sabre element/attribute rename on a version bump silently produces zero
redaction and forwards the response with names in the clear — exactly the fail-open the anchor rule
exists to prevent. (Sibling operations — `GetReservationRS`, `RefundRS`, `eTicketCouponRS`,
`GetElectronicDocumentRS`, `GetTicketingDocumentRS`, `TravelItineraryHistoryRS`, `Trip_SearchRS` — are
already correct with a `required: true` name anchor.)

This is bringing the baked data into compliance with an existing spec requirement; the delta also
clarifies the requirement so the gap is testable per-operation.

## What Changes

- Promote the passenger-name anchor to `required: true` for `AirTicketRS`, `DailySalesReportRS`, and
  `TravelItineraryReadRS`.
- For `GetPriceQuoteRS`, ensure it has a `required: true` passenger-name anchor (add a
  `GetPriceQuoteRS`-scoped name rule if the current shared rule cannot carry the anchor without
  affecting `GetReservationRS`).
- Add per-operation fail-closed golden tests for each newly anchored operation (drift → 502).

## Capabilities

### Modified Capabilities
- `sabre-pii-baseline`: the required-anchor rule is stated to apply to each named PII-heavy operation,
  and the baked ruleset satisfies it for all of them.

## Impact

- `src/channel_relay/pii/rules_fallback.json`: `required: true` on the named anchors; possible new
  `GetPriceQuoteRS`-scoped name rule.
- `tests/`: per-operation fail-closed golden tests (anchor absent → `RedactionError`/502) for the
  four operations; confirm normal-path redaction still passes.
