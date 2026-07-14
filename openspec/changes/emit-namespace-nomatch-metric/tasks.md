# Tasks — emit a warning metric on namespace no-match

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_pii_engine.py`: a field rule with a namespace prefix absent from its declarations → no rewrite AND `channel_relay_rule_namespace_miss_total{channel}` increments; pass does not raise.
- [ ] 1.2 Same for a reference rule path.
- [ ] 1.3 `tests/unit/test_observability.py`: the counter is registered on the metric surface.

## 2. Implementation

- [ ] 2.1 `metrics.py`: define `channel_relay_rule_namespace_miss_total{channel}` and a `record_namespace_miss(channel)` method.
- [ ] 2.2 `engine.py`: thread the metrics handle + channel into the redaction context; in `_locate`, on `XPathError` (or empty result attributable to an undeclared prefix) emit the metric + a warning log, then return `[]`.

## 3. Verify

- [ ] 3.1 Targeted suites green.
- [ ] 3.2 `openspec validate emit-namespace-nomatch-metric --strict`.
- [ ] 3.3 `just ci` green.
