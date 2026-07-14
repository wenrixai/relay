## Why

The relay's implemented content pipeline is XML/SOAP-oriented, but the canonical specification and
engineering documentation still promise JSONPath, inspected MTOM root parts, and inspected deflate.
Those promises are not implemented and make it unclear when the relay must fail closed. In addition,
Amadeus and Travelfusion PII baselines lack the required passenger-name anchors already used for
Sabre, so supplier schema drift can silently turn a covered operation into a no-op. The performance
contract and diagnostics also do not prove or expose the security-sensitive paths they claim to
cover.

Several source-of-truth hygiene issues amplify the ambiguity: the Helm spec still requires a
NetworkPolicy the chart intentionally does not ship, legacy environment compatibility is described
even though it is intentionally deferred, and canonical capability purposes and interim wording were
never cleaned up after archive.

## What Changes

- Define XML/SOAP as the only content format eligible for body inspection. Opaque content remains
  pass-through when inspection is unnecessary; unsupported content fails closed when structural
  credential handling or PII processing requires inspection.
- Restrict PII rules to XPath and reject unsupported path types when a ruleset loads.
- Add required passenger-name anchors for the Amadeus `PNR_Reply` and Travelfusion booking-detail
  baselines, with fail-closed schema-drift behavior.
- Fully specify deterministic encryption, extraction patterns, required rules, XPath evaluation
  error telemetry, and the corresponding bounded `/admin/flare` statistics.
- Correct the Helm contract to state that the chart intentionally emits no NetworkPolicy and make
  the performance contract require a verified 2KB/32KB/256KB scenario matrix.
- Canonicalize both channel route forms and clean stale specification/documentation claims,
  including deferred legacy environment compatibility.

## Capabilities

### New Capabilities

- `amadeus-pii-baseline`: establishes the required anchor and drift behavior for Amadeus PNR
  redaction.
- `travelfusion-pii-baseline`: establishes the required anchor and drift behavior for
  Travelfusion booking-detail redaction.

### Modified Capabilities

- `transparent-relay`: documents both route forms and XML/SOAP-only inspection boundaries.
- `pii-rules`: restricts paths to XPath and specifies deterministic, extraction, and required-rule
  semantics.
- `redaction-engine`: fails closed on required-rule misses and reports XPath evaluation errors.
- `observability`: adds a bounded PII rule-path error counter.
- `admin-diagnostics`: exposes the new counter in the safe in-process statistics snapshot.
- `deployment-ci`: removes the chart-owned NetworkPolicy requirement and strengthens the perf
  scenario/matrix contract.

## Impact

- Runtime: content gating, rule validation, required baseline anchors, metrics, and admin statistics.
- Tests: content boundaries, schema-drift failures, authorization ordering/error cases, metric/admin
  exposure, and perf contract/preflight coverage.
- Documentation: README, engineering/configuration guidance, canonical capability purposes, and
  source comments.
- Compatibility: JSONPath rules become invalid instead of being silently ignored. Deployments that
  require body inspection must send XML/SOAP (gzip is supported); MTOM, JSON, deflate, and unknown
  formats are unsupported for inspection.
