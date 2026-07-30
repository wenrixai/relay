## Why

Upstream TLS server-certificate verification is currently opted out **per channel** via
`tls.insecure_skip_verify` (`ChannelTLS`, added by `2026-07-14-relay-tls-validation-config`). That
buys granularity nobody uses and costs a permanent second httpx connection pool
(`app.state.insecure_client`), a per-request pool-selection branch in the route handler, a second
OTel instrument/uninstrument path, and a `create_app(insecure_http_client=...)` test hook. It also
places a security-weakening switch in the *channel* document, which is customer-supplied config,
rather than in operator-owned process settings.

A relay process should have exactly one upstream TLS policy, owned by the operator, verified by
default.

## What Changes

- Add `RELAY_UPSTREAM_TLS_VERIFY` (`Settings.upstream_tls_verify: bool = True`): the single,
  process-wide upstream TLS verification switch. When `false`, the one shared upstream client is
  built with `verify=False` and **every** channel skips certificate verification.
- **Remove** the `ChannelTLS` model and the `ChannelConfig.tls` field outright. `ChannelConfig` is
  `extra="forbid"`, so a config document still carrying a `tls` block now fails validation and
  aborts startup as an unknown field (breaking; see Migration).
- Remove the second connection pool entirely: `app.state.insecure_client`, the lazy
  `verify=False` client build, the route-handler pool selection, the extra
  instrument/uninstrument branches, and the `create_app(insecure_http_client=...)` parameter.
- `build_http_client` reads `settings.upstream_tls_verify` instead of taking a `verify` kwarg, so
  there is one source of truth for the policy.
- Startup still warns loudly whenever verification is off — once, relay-wide, instead of per channel.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `relay-configuration`: replace the per-channel TLS opt-out requirement with a process-wide
  `RELAY_UPSTREAM_TLS_VERIFY` requirement and a single-upstream-pool guarantee.

## Non-Goals

- Any compatibility shim for the removed field. A deprecated no-op was considered and rejected: it
  leaves dead model code plus a schema field that lies about its effect, and it lets a config keep
  claiming an opt-out the relay no longer honors. Failing loudly at startup matches the repo's
  fail-closed rule.
- Any per-channel TLS granularity in a new form (custom CA bundles, per-channel client certs,
  pinning). A deployment that needs one lax upstream alongside strict ones must isolate it in its
  own relay replica set.

## Impact

- `src/channel_relay/settings.py`: new `upstream_tls_verify: bool = True`.
- `src/channel_relay/config/models.py`: `ChannelTLS` deleted; `ChannelConfig.tls` deleted.
- `src/channel_relay/main.py`: `build_http_client` signature; `warn_insecure_tls_config` becomes
  settings-driven; `_build_upstream_clients` returns a single ownership flag;
  `_instrument_http_clients`/`_uninstrument_http_clients` lose the insecure branch; `create_app`
  loses `insecure_http_client`; `lifespan` closes one client; the relay route drops the pool ternary.
- `openspec/specs/relay-configuration/spec.md`: requirement replaced.
- `docs/PROJECT.md` §5.1, `docs/SECURITY_POSTURE.md` "Upstream TLS", `docs/PROXY_CONFIGURATION_GUIDE.md`
  env reference.
- Tests: `tests/unit/test_config.py`, `tests/unit/test_main_startup.py`,
  `tests/unit/test_settings_validation.py`, and
  `tests/integration/test_tls_insecure_channel.py` → `tests/integration/test_tls_verification.py`.

## Migration

**Breaking.** Any `relay.json` (or `RELAY_CHANNELS_JSON`) still containing a channel `tls` block will
abort startup with a sanitized unknown-field validation error after this upgrade. Before deploying:

1. Delete every `tls` block from channel config.
2. If a channel genuinely relied on `tls.insecure_skip_verify: true`, either fix the upstream
   certificate, or move that channel into its own relay deployment with
   `RELAY_UPSTREAM_TLS_VERIFY=false` — setting that var on a shared process disables verification for
   every channel it serves.
