# Emit a warning metric when a rule path is a namespace no-match

## Why

Both `redaction-engine` and `referential-redaction` specify that a rule whose XPath uses a namespace
prefix absent from its declarations is a **no-match** and that *"a warning metric is emitted, and
processing continues."* The engine implements the no-match but not the metric: `engine.py` `_locate`
catches `etree.XPathError` and returns `[]` silently — no log, no metric call.

Effect: a rule-authoring typo in a namespace prefix (a realistic mistake, since Sabre/Amadeus payloads
use default namespaces that each rule must bind explicitly) produces **zero redaction with zero
operational visibility**. PII can silently forward unredacted and no dashboard shows it. The existing
test only asserts `_locate` does not raise; it never asserts a metric fired.

## What Changes

- On a namespace/XPath no-match in `_locate`, the relay SHALL emit a warning-level metric (a dedicated
  counter, e.g. `channel_relay_rule_namespace_miss_total{channel}`) and a warning log, then continue —
  making the silent-no-redaction case observable.
- Applies to both `field` and `reference` rule paths.

## Capabilities

### Modified Capabilities
- `redaction-engine`: the namespace-no-match scenario names the concrete warning metric that MUST be
  emitted.
- `observability`: add the namespace-miss counter to the metric surface.

## Impact

- `src/channel_relay/pii/engine.py`: emit metric + log from `_locate` (thread the metrics handle /
  channel into the redaction context).
- `src/channel_relay/observability/metrics.py`: define the counter.
- `tests/unit/test_pii_engine.py`, `tests/unit/test_observability.py`: assert the metric increments on
  a namespace-prefix typo.
