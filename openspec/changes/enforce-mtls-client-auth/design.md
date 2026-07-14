# Design — enforce mTLS client authentication

## Context

mTLS terminates at uvicorn (the ASGI server), not in application middleware — client-cert
verification must happen during the TLS handshake, before any request reaches FastAPI. This shapes
the design: the enforcement lever is uvicorn's `ssl_*` configuration in `cli()`, and the app-level
job is limited to (a) fail-closed startup validation and (b) honest diagnostics.

## Decisions

### D1 — Enforce at the transport, verify at the handshake
`cli()` builds the uvicorn run with `ssl_certfile`, `ssl_keyfile`, `ssl_ca_certs`, and
`ssl_cert_reqs=ssl.CERT_REQUIRED` when `mtls_enabled` is true. `CERT_REQUIRED` + a CA bundle makes
the stdlib TLS layer reject a missing or untrusted client cert during the handshake — no per-request
middleware needed, and no way for an unverified request to reach a route.

### D2 — Ship the fail-closed guard independently of full enforcement
The auth-bypass hole is the urgent defect. The guard (`validate_auth_config` aborts when no mechanism
is enforced) is small, testable, and closes the hole even before the TLS wiring lands: a config that
would have served open now refuses to boot. Enforcement (D1) then turns the refusal into a working
mTLS deployment. Both ship in this change; the guard is the safety net that makes a
misconfiguration fail closed regardless.

### D3 — `auth_active` becomes mechanism-aware
`auth_active(settings)` currently means "basic auth is usable." Generalize it to "some client-auth
mechanism is enforceable": basic auth with creds, OR mTLS with complete material. `validate_auth_config`
aborts when neither holds and neither is explicitly disabled. This keeps one source of truth for "is
the data plane protected" that both startup validation and `/admin/flare` read.

### D4 — Diagnostics track enforcement, not intent
`/admin/flare` must report mTLS active only when it is actually enforced (material present + wired),
never merely because the flag is set — the current behavior (reporting the flag verbatim) is what made
the bypass invisible. Derive the reported value from the same predicate `validate_auth_config` uses.

## Risks

- **TLS material distribution.** The CA bundle must be mounted (Helm secret / file). Covered in the
  chart + docs impact; startup abort catches a missing mount.
- **Local/dev ergonomics.** mTLS is opt-in; basic auth remains the default, so dev/test flows are
  unaffected. e2e mTLS tests use a throwaway CA generated in-fixture (no network, stays fast).

## Non-goals

- Certificate revocation (CRL/OCSP) — out of scope for v1; document as a follow-up.
- Per-client certificate identity / authorization — this change authenticates the client channel to
  the relay; it does not introduce per-client policy.
