# Bound uncovered-operation cardinality (memory/metric DoS from upstream)

## Why

`record_uncovered_operation(channel, operation)` (`proxy/forwarder.py`) uses `operation` as an OTel
counter attribute **and** stores it in an in-process dict (`_totals.uncovered_operations[channel][operation]`)
that only ever grows — and the full set is dumped into `/admin/flare`. But `operation` is
`parse_operation(root)`, an element local-name taken from the **upstream response** (`engine.py`).

A malicious or compromised channel on a PII-enabled route returns responses with endlessly varied
root/Body-child element names. Each distinct name is a new uncovered "operation" → the in-process dict
grows without bound (never evicted) → process-memory exhaustion, plus unbounded metrics-backend label
cardinality. The same unbounded set is serialized into the admin diagnostics snapshot.

## What Changes

- Bound the distinct `operation` values tracked per channel for the uncovered-operation signal: cap
  the number of retained keys (e.g. an LRU / first-N with an overflow bucket), or drop the `operation`
  label entirely and keep a per-channel uncovered counter. The metric must remain useful for
  discovering coverage gaps without letting the upstream drive unbounded cardinality.
- The admin snapshot SHALL reflect the bounded set (never an unbounded dump).

## Capabilities

### Modified Capabilities
- `observability`: the coverage-gap metric's `operation` dimension is bounded so an untrusted upstream
  cannot drive unbounded label cardinality or in-process memory growth.

## Impact

- `src/channel_relay/observability/metrics.py`: bound `uncovered_operations` retention (cap distinct
  keys per channel with an overflow bucket, or drop the label).
- `src/channel_relay/proxy/forwarder.py`: unchanged call site (or pass a normalized/bucketed operation).
- `tests/unit/test_observability.py`, `tests/unit/test_admin.py`: feeding many distinct operations
  keeps the retained set (and snapshot) bounded.
