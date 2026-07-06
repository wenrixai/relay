## Why

Client HTTP basic auth fails **open**: when `basic_auth_enabled=True` (the default) but no
username/password is configured, the relay serves the data-plane routes
(`/channel/{name}/{path:path}`) unauthenticated. Those routes decrypt PII and inject real
supplier credentials, so an unconfigured-but-"enabled" relay silently exposes the PII
boundary to any client with network reach. The spec already says auth SHALL be enforced by
default; the fail-open behavior is an implementation deviation with no governing scenario.

## What Changes

- The relay SHALL **abort startup** (refuse to serve) when `basic_auth_enabled` is true but
  either credential is unset — mirroring the existing keyring fail-fast (`build_keyring`).
- Serving routes open remains possible **only** via the explicit, visible
  `basic_auth_enabled=False` (unchanged behavior).
- **BREAKING** (operational): a relay currently running with auth "enabled" but no
  credentials will now fail to boot instead of serving open. Operators must either set
  `RELAY_BASIC_AUTH_USER`/`RELAY_BASIC_AUTH_PASS` or explicitly set
  `RELAY_BASIC_AUTH_ENABLED=false`.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `client-authentication`: add a requirement that the relay fails closed (aborts startup)
  when basic auth is enabled without configured credentials, rather than serving open.

## Impact

- `src/channel_relay/main.py` — startup validation in the lifespan (new helper + call).
- `src/channel_relay/middleware/auth.py` — docstring correction on `auth_active`
  (no longer "serves open" on missing creds).
- Tests: new startup-abort unit test; e2e/integration fixtures updated to set
  `basic_auth_enabled=False` (they currently relied on fail-open to reach `/channel`).
- Operational: deployments must supply credentials or explicitly disable auth.
