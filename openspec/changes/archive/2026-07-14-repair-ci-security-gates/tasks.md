## 1. Regression tests

- [x] 1.1 Add workflow-contract tests for CodeQL permissions, license-free full-history gitleaks, and
      a third-party-only locked dependency audit.
- [x] 1.2 Confirm the new workflow-contract tests fail against the current security workflow.

## 2. Security workflow

- [x] 2.1 Restore `contents: read` in the CodeQL job's least-privilege permissions.
- [x] 2.2 Replace the licensed organization action with the pinned open-source gitleaks container and
      retain full-history checkout plus redacted output.
- [x] 2.3 Exclude the editable relay project from the locked production export and audit it without pip
      dependency resolution.

## 3. Readiness unit test

- [x] 3.1 Reuse the lightweight TestClient fixture for the not-ready endpoint test, keeping the global
      100 ms slow-test budget unchanged.

## 4. Validation

- [x] 4.1 Run focused workflow/readiness tests, actionlint/pre-commit, and the full CI suite.
- [x] 4.2 Validate and archive the OpenSpec change, then validate canonical specs strictly.
