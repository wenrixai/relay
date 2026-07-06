## Context

`select_rules(ruleset, channel, operation)` (`engine.py:213`) returns `[]` for any operation without
rules. `redact_response_body` then runs both phases as no-ops and returns the body unchanged with
empty `counts`. The forwarder's `_response_pii_stage` (`forwarder.py:445`) treats empty counts as
"nothing to redact" and forwards. There is no signal distinguishing "operation has rules, no PII this
time" from "operation has no rules at all." Result: 45 of ~50 Sabre operations forward PII with no
visibility into the gap.

The fix is coverage + observability, not blocking: add rules for the high-priority operations, and
emit a metric when an uncovered operation is forwarded so the remaining gap is discoverable.

Constraints already in place that this design builds on:
- The engine **already** supports `required: true` on `FieldRule` and fails closed (`engine.py:294`).
  No Sabre rule uses it — this change adds anchors, no engine work for `required`.
- `RelayMetrics` (`metrics.py`) already has the counter/totals pattern used by `operations_denied`.
- The engine natively redacts both element text and attributes; no engine change for new rules.

## Goals / Non-Goals

**Goals:**
- Cover the high-priority PII-bearing Sabre operations.
- Make the remaining coverage gap observable via a metric (never silent).
- Fail closed on Sabre schema drift for **covered** operations via `required` anchors.

**Non-Goals:**
- Blocking or erroring on uncovered operations. Uncovered operations are forwarded unchanged, exactly
  as today.
- Any per-channel policy configuration (block/warn/allow), PII-free allowlist, or cryptic-screen
  opt-in. Not introduced.
- Regex screen-scraping redaction of `SabreCommandRS` cryptic dumps.
- Covering every one of the ~50 operations in this slice — only the high-priority list; the rest are
  forwarded and surfaced by the metric.
- Any change to the `ENC_` token format, crypto, or de-anonymization path.

## Decisions

### D1: Surface a coverage outcome from the engine, emit the metric in the forwarder
`redact_response_body` returns `(bytes, counts)`. Extend it to also report whether any rule matched
the operation — add `covered: bool` + `operation: str`, computed from `_select_rules_for_channels`
being non-empty (the same selection it already does). The forwarder emits
`pii_uncovered_operation_total` when a PII-enabled response is uncovered, then forwards the body
unchanged. The engine stays pure (no metrics handle); the forwarder owns the metric because it holds
the channel + metrics context.

*Alternative rejected:* infer coverage from `counts == {}`. Wrong — a covered operation with no PII
in this particular response also yields empty counts, so the metric would fire constantly.

### D2: `required: true` on one anchor per PII-heavy operation
The passenger-name rule is the anchor. If Sabre renames elements on a version bump, the anchor
locates nothing → `RedactionError` → 502. This applies only to operations we **do** cover, and only
fires on drift — it is not a policy on uncovered operations. One anchor per operation (not every
rule) keeps false-positive failures low while catching structural drift on the field that matters
most.

### D3: Author rules from the Wenrix parsing models
The XPaths come from `sources/{itinerary,ticketing,pnr,history,queue,sales_report}.py` in the Wenrix
repo — the de-facto schema of what the caller reads. Use the `channel-implementation` skill for rule
authoring and sanitized-fixture conventions.

## Risks / Trade-offs

- **[Compressed responses hide the operation and the PII.]** Sabre search responses can be wrapped in
  `<CompressedResponse>` (base64 gzip inside the XML). The relay parses the SOAP body and sees only
  the opaque blob — neither the real operation name nor the PII inside it. The coverage metric will
  flag such responses as uncovered (unknown operation). → Structured redaction cannot reach the
  payload; out of scope here, flagged as Open Question.
- **[Anchor `required` false positives.]** A legitimately name-less response for a "PII-heavy" op
  would 502. → Mitigation: pick anchors that are structurally always present for that operation;
  golden fixtures assert the anchor matches.
- **[Uncovered PII still flows.]** By design, uncovered operations forward plaintext PII; the metric
  makes this visible but does not stop it. Closing the gap is done by adding rules, guided by the
  metric.

## Migration Plan

Additive; no config changes, no behavior change for existing traffic beyond the new metric and the
newly covered operations redacting. No rollback concerns. Operators watch
`pii_uncovered_operation_total` to prioritize which remaining operations need rules.

## Open Questions

- Should `CompressedResponse` be decoded-then-redacted in a follow-up change, or should PII-enabled
  Sabre channels be required to disable application-level compression? (Leaning: follow-up change.)
