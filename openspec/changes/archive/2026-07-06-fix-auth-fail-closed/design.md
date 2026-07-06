## Context

`verify_basic_auth` (the dependency on `/channel/{name}/{path:path}`) returns without a
challenge whenever `auth_active(settings)` is false. `auth_active` is false when
`basic_auth_user` or `basic_auth_pass` is unset, which is the default (`basic_auth_enabled`
defaults to `True`, both credential fields to `None`). Result: an "enabled" relay with no
configured credentials serves the PII-decrypting, credential-injecting routes open.

The codebase already has a fail-fast idiom for a security-required-but-missing input:
`build_keyring` (`main.py:40-60`) raises `RuntimeError` from the lifespan (`main.py:105`)
when a channel needs encryption but no keyring is configured, aborting startup.

## Goals / Non-Goals

**Goals:**
- Make basic auth fail closed: an enabled-but-unconfigured relay must not serve open.
- Reuse the existing startup fail-fast pattern for consistency and loud failure.
- Keep the explicit `basic_auth_enabled=False` open path intact.

**Non-Goals:**
- Changing credential comparison, header parsing, or the admin route (already fail-closed).
- Adding per-request rejection logic — startup abort is sufficient and stronger.
- mTLS or any new auth mechanism.

## Decisions

- **Abort at startup, not per-request.** Add a check in the lifespan (next to and before
  `build_keyring`) that raises `RuntimeError` when
  `settings.basic_auth_enabled and not auth_active(settings)`. A misconfigured relay
  crashloops loudly rather than appearing "up" while unauthenticated. Chosen over a
  request-time 401 because it makes the misconfiguration unrunnable and matches the
  established `build_keyring` template (with an existing test pattern to mirror).
- **`verify_basic_auth` unchanged.** Post-startup-check, `auth_active` is false only when
  auth is explicitly disabled, so the existing open-return is correct. Fix the misleading
  `auth_active` docstring that claims it "serves open" / "logs at startup".

## Risks / Trade-offs

- **Operational breakage:** relays currently running enabled-but-unconfigured will fail to
  boot. This is the intended safety outcome; documented in the proposal as BREAKING.
  Mitigation: explicit error message naming the two env vars, and the
  `RELAY_BASIC_AUTH_ENABLED=false` escape hatch.
- **Test blast radius:** e2e/integration fixtures relied on fail-open to reach `/channel`.
  They must set `basic_auth_enabled=False`. Low risk, mechanical, and it makes each
  suite's auth posture explicit.
