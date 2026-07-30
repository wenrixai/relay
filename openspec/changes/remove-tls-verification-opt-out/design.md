## Context

`2026-07-14-relay-tls-validation-config` introduced a per-channel opt-out and, with it, a dual-pool
design: `app.state.client` (verifying) plus a lazily built `app.state.insecure_client`
(`verify=False`), selected per request in the relay route
(`main.py:422`, `insecure_client if channel.tls.insecure_skip_verify else client`). Everything that
touches the client is therefore doubled: construction, ownership flags, OTel
`instrument_client`/`uninstrument_client`, teardown `aclose`, and the `create_app` test hook. The
opt-out also lives in the channel document — customer-supplied config — and `main.py` carries a
`warn_insecure_tls_config` startup warning whose only purpose is to apologise for it.

## Goals / Non-Goals

**Goals:**
- Upstream TLS server-certificate verification is unconditional, with no configuration surface at any
  level (channel or process) that can turn it off.
- Collapse the dual-pool machinery back to a single client.
- Leave no dead field, setting, or warning behind.

**Non-Goals:**
- A relay-wide replacement switch; a compatibility shim for the removed field; custom CA bundles or
  pinning (see proposal Non-Goals).

## Decisions

**1. Zero switches, not one relay-wide switch.**
A process-level `RELAY_UPSTREAM_TLS_VERIFY` was drafted and rejected. It does not fix the actual
problem — an unverified upstream on the path where the relay hands over de-anonymized PII — it only
moves who gets to make that mistake and widens the blast radius from one channel to every channel the
process serves. A flag that exists gets used: the presence of a documented "ignore certificates"
setting is itself the failure mode, because it is always the fastest way past a handshake error at
3am. With no switch, a bad certificate is a certificate problem and gets a certificate fix.

**2. `build_http_client` loses the `verify` argument rather than defaulting it to `True`.**
Keeping `verify: bool = True` would leave the non-verifying path one keyword away and invite a future
call site to reach for it. Deleting the parameter means the only client the relay can construct is a
verifying one, and httpx's own default carries the behavior — nothing to keep in sync.

**3. `warn_insecure_tls_config` is deleted, not repurposed.**
The warning existed to surface a weakened posture. With the posture no longer expressible there is
nothing to report; keeping a "TLS is on" info line would be noise on every boot. `warn_unenforced_config`
stays as-is — `authorization.external` really is accepted-but-unenforced.

**4. Hard removal of `ChannelTLS` / `ChannelConfig.tls`, no deprecated no-op.**
Because `ChannelConfig` is `extra="forbid"`, deleting the field turns a leftover `tls` key into a
sanitized config-validation error and a startup abort. A one-release accept-and-ignore shim was
considered and rejected: it keeps dead model code plus a published JSON Schema field that no longer
does what it says, and it lets a config keep asserting an opt-out the relay silently does not honor.
Aborting is the repo's fail-closed default for misconfiguration, and the failure is loud, immediate,
and caught at deploy time rather than at the first upstream call.

**5. A private-CA upstream is served by the trust store, not by a flag.**
The legitimate case behind most `insecure_skip_verify` usage is an upstream with an internal CA. The
supported answer is to add that CA to the relay's trust store (baked into the image or mounted and
pointed at via the standard OpenSSL/certifi environment), which keeps verification on. If that proves
awkward in practice, the follow-up is an explicit CA-bundle setting — additive, and it never disables
verification.

## Risks / Trade-offs

- **[Risk]** A deployment that still ships a `tls` block fails to start after upgrade. Accepted and
  intended — the alternative is a config that silently means nothing. Mitigated by the Migration
  section; the abort names the offending field path (never its value).
- **[Risk]** A channel whose upstream presents an unverifiable certificate becomes unusable until the
  certificate or trust store is fixed, with no configuration escape hatch. Accepted: that is the point
  of the change, and failing closed on an unverifiable peer is the correct outcome for a relay that
  forwards de-anonymized PII.
- **[Trade-off]** Losing the per-channel escape hatch removes a debugging convenience against test/
  staging upstreams with self-signed certificates. Those environments can mount the self-signed CA
  into the relay's trust store, which is the same mechanism production uses.
