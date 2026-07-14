# Add the CLI-equivalent admin diagnostics subcommand

## Why

`docs/PROJECT.md` §12.7 requires a redacted admin/status view *"(and an equivalent CLI subcommand)"*.
The HTTP half shipped as `GET /admin/flare` (covered by the `admin-diagnostics` spec), but the CLI
equivalent is absent from both the code and OpenSpec: `cli()` (`main.py`) only runs uvicorn, and there
is no subcommand that prints the redacted diagnostics snapshot. Operators cannot inspect the redacted
state locally (e.g. inside a container, or before the HTTP listener is reachable) without curling the
authenticated route.

## What Changes

- Add a CLI subcommand (e.g. `channel-relay status`) that prints the **same** redacted diagnostics
  snapshot as `GET /admin/flare` — config summary, active channels (name/type/host, swap-configured
  bool, pii-enabled bool), `rules_version`, available key epochs (ids only), telemetry state, and
  readiness reasons — with the identical redaction guarantees (no credential values, no keyring
  material, no PII, no auth secrets).
- The snapshot builder SHALL be shared between the HTTP route and the CLI so the two never diverge.

## Capabilities

### Modified Capabilities
- `admin-diagnostics`: the redacted snapshot is available via a CLI subcommand in addition to the
  authenticated HTTP route, from the same shared builder.

## Impact

- `src/channel_relay/main.py` / `admin.py`: a `status` CLI subcommand reusing the snapshot builder.
- `tests/unit/test_admin.py`: assert the CLI output matches the route's redaction guarantees (no
  secrets/PII/keys) and includes the documented fields.
- `docs/`: document the subcommand.
