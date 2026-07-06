## Why

The baked Sabre ruleset covers only 5 of the ~50 operations the Wenrix Sabre service uses. Every
uncovered PII-bearing response (PNR create echo, passenger details, ticketing/refund/exchange
documents, queue lists, past-date PNRs) is forwarded to the client in plaintext, and — because
`select_rules` returning `[]` is indistinguishable from "nothing to redact" — the gap is invisible
to operators. The fix is to cover the high-priority operations and make any remaining gap
**discoverable via a metric**, not to block traffic.

## What Changes

- **Expand the Sabre baseline** with `field`/`reference` rules for the high-priority uncovered
  response operations actively used by Wenrix handlers: `CreatePassengerNameRecordRS`,
  `PassengerDetailsRS`, `TravelItineraryHistoryRS`, `GetTicketingDocumentRS` / `GetETicketDetailsRS`,
  `GetTicketInformationFromAirlineRS`, `TicketRefundRS`, `TicketExchangeRS`, `DailyRefundReportRS`,
  `PastDatePnrDetailsRS`, and `QueueAccessRS`. XPaths sourced from the Wenrix parsing models
  (`sources/itinerary.py`, `ticketing.py`, `pnr.py`, `history.py`, `queue.py`, `sales_report.py`).
- **Coverage observability, not blocking.** Uncovered operations are still forwarded unchanged
  (unchanged behavior). The relay additionally emits `pii_uncovered_operation_total{channel,
  operation}` whenever a PII-enabled response operation matches zero rules, so gaps are discoverable
  instead of silent. No new configuration, no fail-closed on uncovered operations.
- **`required: true` anchors** on the passenger-name rule of each PII-heavy operation so Sabre schema
  drift (element/attribute renames on version bumps) on a **covered** operation fails closed (502)
  instead of silently leaking. This is the existing engine `required` behavior; no Sabre rule uses it
  today.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `sabre-pii-baseline`: expand covered operations beyond the original 5; add `required: true` anchors.
  Uncovered operations remain forwarded unchanged.
- `redaction-engine`: the response-redaction pass SHALL report whether the parsed operation matched
  any rules (coverage outcome) so the forwarder can emit the coverage metric. Behavior for uncovered
  operations is unchanged (forwarded as-is).
- `observability`: add the `pii_uncovered_operation_total{channel, operation}` counter.

## Impact

- Code: `src/channel_relay/pii/engine.py` (surface coverage outcome), `proxy/forwarder.py`
  (`_response_pii_stage` emits the metric on an uncovered PII-enabled response),
  `observability/metrics.py` (new counter), `pii/rules_fallback.json` (new Sabre rules + `required`
  anchors).
- Fixtures/tests: sanitized fixtures per new operation in `tests/fixtures/sabre/`; golden unit +
  relay integration tests; metric test.
- No new dependencies, no new configuration fields, no change to the `ENC_` token format or crypto.
