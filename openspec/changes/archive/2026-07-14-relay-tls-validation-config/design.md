## Context

The relay forwards every channel's traffic through a single shared `httpx.AsyncClient`
(`main.py:build_http_client`), stored on `app.state.client` and injected into `forward()`
(`proxy/forwarder.py`). httpx verifies the upstream TLS certificate by default and there is no
per-channel override. `ChannelConfig` (`config/models.py`) already has the established pattern for
per-channel opt-in toggles (`pii`, `credentials`, `authorization`), each its own nested model,
`extra="forbid"`, default `false`/disabled.

## Goals / Non-Goals

**Goals:**
- Let one channel skip upstream TLS certificate verification without affecting any other channel.
- Default stays verifying (`false`) so existing deployments are unaffected.
- Make the opt-out visible in startup diagnostics (WARNING log), matching the existing pattern for
  `authorization.external` (accepted-but-notable config).
- Keep `forward()`'s signature and pipeline stages untouched — this is a transport-layer concern
  resolved before `forward()` is called.

**Non-Goals:**
- No client-certificate (mTLS) support — this only disables server certificate verification.
- No per-request or per-operation override — the flag is per-channel, set once at config load.
- No change to the PII crypto path, credential swap, or token format.
- Not building a full custom CA/trust-bundle system — this is a binary skip, matching httpx's
  `verify=False`.

## Decisions

**One extra shared client, not one client per channel.** httpx clients are pooled resources; the
relay already has exactly one "trusted" pool. Add exactly one more pool — `insecure_client`, built
with `verify=False` — shared by every channel that opts out. This mirrors `build_http_client`'s
existing shape (`transport=httpx.AsyncHTTPTransport(retries=0, limits=...)`) and avoids a
per-channel connection-pool explosion. Alternative considered: per-channel `httpx.AsyncClient`
instances — rejected as unnecessary; `verify` is the only axis that needs to vary today, and a single
extra pool covers it.

**Lazy construction.** `insecure_client` is only built in `lifespan()` when
`any(c.tls.insecure_skip_verify for c in config.channels)`; a deployment with no insecure channels
never pays for the second pool or its idle keep-alives. This mirrors the existing `owns_client` guard
for the primary client's lifecycle and cleanup (`aclose()` only for what was actually created).

**Client selection happens in the route handler, not `forward()`.** `relay()` in `main.py` picks
`insecure_client` vs. `client` based on `channel.tls.insecure_skip_verify` before calling `forward()`.
`forward()` keeps taking a single `client: httpx.AsyncClient` parameter — its job is pipeline stages,
not client selection. This keeps the existing unit tests for `forward()` (which pass an explicit
client) unaffected.

**New nested model `ChannelTLS`, not a bare boolean field.** Matches the existing style
(`ChannelPII`, `Authorization`) so a future TLS-related knob (e.g. a custom CA bundle) has a natural
home without a breaking field rename. `model_config = ConfigDict(extra="forbid")` like its siblings.

**Startup WARNS, does not abort.** Every other fail-closed startup check in `main.py`
(`validate_auth_config`, `validate_credential_config`) guards against *accidental* misconfiguration
that would silently break security invariants (e.g., credential swap enabled with no auth). Here the
operator is deliberately disabling a security control for a specific known upstream; failing closed
would make the explicit opt-in unusable. This follows the same shape as
`warn_unenforced_config` for `authorization.external` — log loud, proceed.

## Risks / Trade-offs

- **[Risk]** A channel misconfigured with `insecure_skip_verify: true` silently accepts a
  MITM'd upstream connection. → **Mitigation**: default false; startup WARNING names the channel
  every time the process boots, so it's visible in logs/`/admin/flare` diagnostics review, not just
  buried in a config file.
- **[Risk]** Two long-lived connection pools instead of one increases idle resource usage when the
  flag is used. → **Mitigation**: lazy construction — the second pool only exists when at least one
  channel needs it.
- **[Trade-off]** The insecure client is shared across all opted-out channels rather than isolated
  per channel. Acceptable: verification is off for those channels regardless; pool sharing doesn't
  change the security posture, only connection reuse.

## Migration Plan

Additive, backward-compatible: omitting `tls` on any channel preserves current (verifying) behavior.
No data migration. Rollback is simply removing the field from `relay.json` and redeploying.

## Open Questions

None outstanding.
