# Enforce mTLS client authentication (close the auth-bypass hole)

## Why

`docs/PROJECT.md` §9.2 and locked decision D8 document mTLS as the opt-in alternative to basic
auth ("verify the client against the Wenrix certificate baked into the image"). The settings exist
but nothing enforces them:

- `Settings.mtls_enabled` / `tls_enabled` / `tls_port` are read **only** by `admin.py` to render
  `/admin/flare`. A repo-wide search finds no peer-cert verification, no `ssl_context`, no
  `client_cert` handling anywhere.
- `validate_auth_config` (`main.py:64`) and `auth_active` (`middleware/auth.py:21`) reason **only**
  about `basic_auth_enabled`. They have no knowledge of `mtls_enabled`.
- `cli()` (`main.py`) calls `uvicorn.run()` with no `ssl_*` args.

**Result — unauthenticated data plane.** An operator following the documented pattern to switch
client-auth mechanism — `RELAY_BASIC_AUTH_ENABLED=false` + `RELAY_MTLS_ENABLED=true` — boots a relay
where every `/channel/*` and `/admin/flare` route is served with **no authentication at all**.
Startup does not abort, and `/admin/flare` reports `mtls_enabled: true` as though the route were
protected. This is a critical auth bypass and directly contradicts the fail-closed golden rule.

## What Changes

Two parts — a fail-closed guard shipped first, then real enforcement:

1. **Fail closed immediately.** Startup SHALL abort unless at least one client-auth mechanism is
   actively enforced. Enabling `mtls_enabled` without the enforcement wiring, or disabling basic auth
   without an active alternative, aborts with a clear error rather than serving open.
2. **Implement mTLS enforcement.** When `mtls_enabled` is true, uvicorn is configured with a TLS
   context that requires and verifies a client certificate against the baked Wenrix CA; requests
   without a valid client cert are rejected at the transport layer. `auth_active` accounts for mTLS
   so the fail-closed guard passes only when enforcement is real.

## Capabilities

### Modified Capabilities
- `client-authentication`: mTLS is enforced (not merely reported); the fail-closed rule covers the
  full client-auth surface, not just basic auth.

## Impact

- `src/channel_relay/settings.py`: mTLS material (CA/cert/key paths) as validated settings.
- `src/channel_relay/main.py`: `validate_auth_config` covers mTLS; `cli()` builds the uvicorn TLS
  context (`ssl_certfile`/`ssl_keyfile`/`ssl_ca_certs`/`ssl_cert_reqs=CERT_REQUIRED`).
- `src/channel_relay/middleware/auth.py`: `auth_active` returns true for a correctly configured mTLS
  deployment.
- `deployment/helm/chart/`, `docs/`: document the mTLS material mounts.
- `tests/unit/test_main_startup.py`, `tests/unit/test_settings_validation.py`,
  `tests/e2e/`: fail-closed + enforcement tests.
