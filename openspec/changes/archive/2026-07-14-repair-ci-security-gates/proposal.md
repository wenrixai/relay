## Why

The CI and security workflows are configured on pull requests but currently fail before they can
evaluate repository changes: CodeQL cannot check out the private repository, the gitleaks action
requires an unconfigured commercial organization license, and the dependency audit tries to install
the editable relay project from a hash-locked requirements export. A readiness unit test also performs
unrelated application-lifespan work and intermittently exceeds the repository's 100 ms unit-test
budget.

## What Changes

- Restore the least-privilege repository read permission required by CodeQL checkout.
- Run the pinned open-source gitleaks scanner directly against the complete checked-out history,
  without relying on an optional license secret.
- Audit only locked third-party production dependencies and avoid unnecessary pip resolution.
- Add static workflow-contract tests so scanner setup regressions fail locally before GitHub Actions.
- Keep the global 100 ms test budget and make the not-ready endpoint unit test avoid unrelated startup
  and rule-loading work.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `deployment-ci`: require security jobs to execute on organization pull requests using standard
  repository credentials and fail on findings rather than scanner setup.

## Impact

- `.github/workflows/security.yml`: permissions and scanner invocation changes.
- `tests/deployment/`: workflow-contract coverage.
- `tests/unit/test_health.py`: isolate the readiness unit test from application startup.
- No production API, runtime configuration, dependency, or lockfile changes.
