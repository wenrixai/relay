## Why

Upstream TLS server-certificate verification can currently be turned off **per channel** via
`tls.insecure_skip_verify` (`ChannelTLS`, added by `2026-07-14-relay-tls-validation-config`). That
opt-out buys granularity no deployment uses and costs a permanent second httpx connection pool
(`app.state.insecure_client`), a per-request pool-selection branch in the route handler, a second
OTel instrument/uninstrument path, and a `create_app(insecure_http_client=...)` test hook. Worse, it
puts a security-weakening switch in the *channel* document, which is customer-supplied config.

The relay is a privacy-first component sitting between a customer and a travel channel. An
unverified upstream connection is exactly the position an attacker needs to read or rewrite
de-anonymized PII in flight. There is no configuration shape in which that trade is acceptable, so
the correct number of ways to disable verification is zero.

## What Changes

- **Remove the opt-out entirely.** Upstream TLS server-certificate verification is unconditional:
  there is no per-channel field, no `RELAY_*` setting, and no code path that builds a non-verifying
  client.
- Delete the `ChannelTLS` model and the `ChannelConfig.tls` field. `ChannelConfig` is
  `extra="forbid"`, so a config document still carrying a `tls` block now fails validation and
  aborts startup as an unknown field (breaking; see Migration).
- Remove the second connection pool: `app.state.insecure_client`, the lazy `verify=False` client
  build, the route-handler pool selection, the extra instrument/uninstrument branches, and the
  `create_app(insecure_http_client=...)` parameter.
- Remove `warn_insecure_tls_config` — with no way to disable verification there is nothing to warn
  about.
- `build_http_client` no longer takes a `verify` argument; the one shared client always verifies.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `relay-configuration`: replace the per-channel TLS opt-out requirement with a requirement that
  upstream TLS verification is mandatory and not configurable, served by a single upstream pool.

## Non-Goals

- A process-level replacement switch (e.g. `RELAY_UPSTREAM_TLS_VERIFY`). Considered and rejected: a
  relay-wide "ignore certificates" flag is the same unacceptable trade with a larger blast radius,
  and its mere existence invites an operator to reach for it instead of fixing a certificate.
- Any compatibility shim for the removed field. A deprecated no-op would leave dead model code plus a
  published JSON Schema field that no longer does what it says, and would let a config keep asserting
  an opt-out the relay does not honor. Failing loudly at startup matches the repo's fail-closed rule.
- Custom CA bundles, per-channel client certificates, or pinning. An upstream with a private CA is a
  trust-store problem (mount the CA into the image/pod), not a verification-off problem — a future
  change may add an explicit CA-bundle setting, which is additive and never weakens verification.

## Impact

- `src/channel_relay/config/models.py`: `ChannelTLS` deleted; `ChannelConfig.tls` deleted.
- `src/channel_relay/main.py`: `build_http_client` loses its `verify` argument;
  `warn_insecure_tls_config` deleted; `_build_upstream_clients` collapses to a single-client
  `_build_upstream_client`; `_instrument_http_clients`/`_uninstrument_http_clients` lose the insecure
  branch; `create_app` loses `insecure_http_client`; `lifespan` closes one client; the relay route
  drops the pool ternary.
- `openspec/specs/relay-configuration/spec.md`: requirement replaced.
- `docs/PROJECT.md` §5.1, `docs/SECURITY_POSTURE.md` "Upstream TLS",
  `docs/PROXY_CONFIGURATION_GUIDE.md`.
- Tests: `tests/unit/test_config.py`, `tests/unit/test_main_startup.py`, and
  `tests/integration/test_tls_insecure_channel.py` → `tests/integration/test_tls_verification.py`.

## Migration

**Breaking.** Any `relay.json` (or `RELAY_CHANNELS_JSON`) still containing a channel `tls` block will
abort startup with a sanitized unknown-field validation error after this upgrade. Before deploying:

1. Delete every `tls` block from channel config.
2. If a channel relied on `tls.insecure_skip_verify: true`, fix the certificate side: obtain a
   certificate the relay's trust store accepts, or mount the upstream's private CA into the relay's
   trust store. There is no longer any way to skip verification.
