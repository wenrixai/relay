# Tasks — bound uncovered-operation cardinality

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_observability.py`: recording N (N ≫ cap) distinct uncovered operations on one channel → retained distinct keys ≤ cap (overflow folded into a bucket, or label dropped).
- [ ] 1.2 `tests/unit/test_admin.py`: the diagnostics snapshot's uncovered-operation set is bounded under the same load.

## 2. Implementation

- [ ] 2.1 `metrics.py`: bound `uncovered_operations` retention per channel (cap + `__other__` overflow bucket, or drop the `operation` label and keep a per-channel counter). Apply the same bound to the exported OTel attribute set.
- [ ] 2.2 Keep the metric meaningful for coverage-gap discovery (distinct real operations still visible up to the cap).

## 3. Verify

- [ ] 3.1 Targeted suites green.
- [ ] 3.2 `openspec validate bound-uncovered-operation-cardinality --strict`.
- [ ] 3.3 `just ci` green.
