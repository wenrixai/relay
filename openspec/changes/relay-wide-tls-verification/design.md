## Context

`2026-07-14-relay-tls-validation-config` introduced a per-channel opt-out and, with it, a dual-pool
design: `app.state.client` (verifying) plus a lazily built `app.state.insecure_client`
(`verify=False`), selected per request in the relay route
(`main.py:422`, `insecure_client if channel.tls.insecure_skip_verify else client`). Everything that
touches the client is therefore doubled: construction, ownership flags, OTel
`instrument_client`/`uninstrument_client`, teardown `aclose`, and the `create_app` test hook.

Process-level knobs in this codebase already live on `Settings` as `RELAY_*` scalars
(`settings.py`), and the inbound-listener names `tls_enabled`/`tls_port` are already taken — so the
new field needs the "upstream" qualifier to avoid reading as an inbound setting.

## Goals / Non-Goals

**Goals:**
- One upstream TLS policy per relay process, owned by the operator via `RELAY_*`, verifying by default.
- Collapse the dual-pool machinery back to a single client.
- Keep the "loud warning whenever transport security is weakened" property.
- Leave no way for a channel document to weaken transport security.

**Non-Goals:**
- Compatibility shim for the removed field; any replacement per-channel TLS granularity.

## Decisions

**1. Positive setting name `RELAY_UPSTREAM_TLS_VERIFY` (default `true`), not `RELAY_INSECURE_SKIP_VERIFY`.**
A positive boolean whose safe value is the default reads correctly in a manifest diff
(`RELAY_UPSTREAM_TLS_VERIFY: "false"` is visibly an override of a secure default), and it cannot be
misread as "enable TLS" the way `insecure_*` names invite double negatives. `upstream_` is required:
`tls_enabled`/`tls_port`/`mtls_enabled` on the same model all describe the *inbound* listener.

**2. `build_http_client` reads the setting instead of taking `verify: bool`.**
Alternative considered: keep `build_http_client(settings, *, verify=...)`. Rejected — with the second
pool gone there is exactly one caller and one policy, and a kwarg would let a future call site
silently diverge from the configured policy. Tests exercise both paths by constructing
`Settings(upstream_tls_verify=...)`, which is also what production does.

**3. Hard removal of `ChannelTLS` / `ChannelConfig.tls`, no deprecated no-op.**
Because `ChannelConfig` is `extra="forbid"`, deleting the field turns a leftover `tls` key into a
sanitized config-validation error and a startup abort. A one-release no-op (accept, ignore, warn) was
considered and rejected: it keeps dead model code plus a published JSON Schema field that no longer
does what it says, and it lets a config keep asserting an opt-out the relay silently does not honor.
Aborting is the repo's fail-closed default for misconfiguration, and the failure is loud, immediate,
and caught at deploy time rather than at the first upstream call.

**4. One relay-wide warning, fired from `Settings`, not per channel.**
The warning must state the blast radius (all channels), because that is exactly the mistake the old
per-channel flag let operators make. It does not abort: an explicit operator-set env var is a decision,
not a misconfiguration. Mirrors `warn_unenforced_config`'s "accepted but notable" shape.

## Risks / Trade-offs

- **[Risk]** A deployment that still ships a `tls` block fails to start after upgrade. Accepted and
  intended — the alternative is a config that silently means nothing. Mitigated by the Migration
  section and by the fact that the abort names the offending field path (never its value).
- **[Risk]** A deployment that relied on the per-channel opt-out and reacts by setting
  `RELAY_UPSTREAM_TLS_VERIFY=false` weakens every other channel in that process. Mitigated by the
  startup WARNING naming the blast radius, and by documenting replica-set isolation as the supported
  alternative.
- **[Trade-off]** Losing per-channel granularity means a single lax upstream forces either a
  certificate fix or a dedicated deployment. Accepted: no deployment used the granularity, and the
  cost was a permanently doubled client path.
