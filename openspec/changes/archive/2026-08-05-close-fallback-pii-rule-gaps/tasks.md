## 1. Failing tests first

- [x] 1.1 Extend sanitized fixtures with populated fax and Travelport state evidence where needed.
- [x] 1.2 Add Travelfusion assertions for phone leaves, DOB, age, title, custom identity fields, and client IP.
- [x] 1.3 Add Farelogix assertions for DOCS, title, and document metadata.
- [x] 1.4 Add a Travelport assertion for state redaction.
- [x] 1.5 Add strict rule-model coverage for `age` and `ip_address`.

## 2. Baked rules and model

- [x] 2.1 Add the two PII types and update canonical documentation.
- [x] 2.2 Correct and expand Travelfusion rules without adding required anchors.
- [x] 2.3 Expand Farelogix identity-document and title rules.
- [x] 2.4 Expand Travelport address leaves without changing structured-name coverage.
- [x] 2.5 Bump `rules_version`.

## 3. Verify and archive

- [x] 3.1 Run focused unit and integration suites.
- [x] 3.2 Run `just ci` and the thermo-nuclear quality review.
- [x] 3.3 Validate and archive the OpenSpec change.
