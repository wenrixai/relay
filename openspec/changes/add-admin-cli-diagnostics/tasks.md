# Tasks — add the CLI-equivalent admin diagnostics subcommand

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_admin.py`: the CLI subcommand output includes the documented fields (channels, rules_version, epoch ids, telemetry, readiness reasons).
- [ ] 1.2 No-leak test: CLI output contains no credential values, no keyring material, no PII, no auth secrets — even when creds + keyring are configured.
- [ ] 1.3 Parity test: CLI snapshot content equals the `/admin/flare` snapshot for the same app state.

## 2. Implementation

- [ ] 2.1 Extract the redacted-snapshot builder (if not already shared) so both the route and CLI use it.
- [ ] 2.2 Add a `status` subcommand to `cli()` that builds the snapshot and prints it (JSON), exit 0.

## 3. Docs

- [ ] 3.1 Document the subcommand in `docs/`.

## 4. Verify

- [ ] 4.1 `openspec validate add-admin-cli-diagnostics --strict`.
- [ ] 4.2 `just ci` green.
