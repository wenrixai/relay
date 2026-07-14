## 1. Source-of-truth reconciliation

- [x] 1.1 Archive the completed `remove-helm-networkpolicy` and
  `harden-relay-config-validation` changes so their deltas are canonical.
- [x] 1.2 Remove live legacy environment-compatibility claims from documentation and source comments;
  do not rewrite archived changes or Git history.
- [x] 1.3 Replace generated `TBD` capability purposes and stale interim wording, and document both
  supported channel route forms.
- [x] 1.4 Update engineering/customer documentation to describe XML/SOAP-only inspection, gzip XML
  support, opaque no-inspection pass-through, and fail-closed unsupported inspected content.

## 2. Content and rules contracts

- [x] 2.1 Add request/response content gates and the stable `unsupported_content_type` reason.
- [x] 2.2 Restrict rule `path_type` validation to XPath and regenerate the rules JSON Schema.
- [x] 2.3 Specify and test deterministic encryption, extraction-pattern capture/overlap behavior,
  and required-rule fail-closed behavior.
- [x] 2.4 Mark the Amadeus and Travelfusion passenger-name anchors required and bump the baked
  `rules_version`.

## 3. Diagnostics and performance

- [x] 3.1 Record bounded XPath evaluation errors in OTel and in-process metrics, emit safe warnings,
  and expose totals through authenticated `/admin/flare` statistics.
- [x] 3.2 Repair each perf scenario so its intended pipeline stages execute, add a semantic preflight,
  and run/publish the full payload-size matrix.

## 4. Verification

- [x] 4.1 Add schema-drift, content-boundary, operation-authorization ordering/error, metric/admin,
  and perf-contract tests.
- [x] 4.2 Run targeted suites, strict OpenSpec validation, the `just ci` component gates,
  `just helm-test`, and a live four-stage perf preflight. The local k6 smoke is deferred to the CI
  matrix because k6 is not installed in this environment.
- [x] 4.3 Archive this change only after all implementation and verification tasks pass.
