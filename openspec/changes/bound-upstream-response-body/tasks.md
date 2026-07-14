# Tasks — bound the upstream response body

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_forwarder.py`: a small gzip-bomb upstream response on a PII/redaction channel → rejected with the defined error, body never fully materialized (assert no multi-GB allocation via a cap probe).
- [ ] 1.2 A plain oversize upstream response on an inspected channel → rejected.
- [ ] 1.3 A compressed upstream bomb on a pass-through channel → stopped at the global ceiling.
- [ ] 1.4 Normal-size responses (compressed and plain) on inspected + pass-through channels → forwarded unchanged.

## 2. Implementation

- [ ] 2.1 Replace the unbounded `upstream.content` read with a bounded read (stream + cap) — reuse the request-path bounded-decode helper for the response direction.
- [ ] 2.2 Reject an oversize inspected response before the redaction/credential stages; apply a global ceiling for pass-through.
- [ ] 2.3 Decide the response error shape (413 vs 502) and wire it through `proxy/errors.py`.

## 3. Verify

- [ ] 3.1 Targeted suites green.
- [ ] 3.2 `openspec validate bound-upstream-response-body --strict`.
- [ ] 3.3 `just ci` green.
