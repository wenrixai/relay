## Context

`SoapSecurityHandler.swap_request_body` (`src/channel_relay/channels/handlers.py:307-317`) replaces
the whole `<Security>` element on every credentialed SOAP request, gated only by
`requires_body_inspection = bool(credential_values)` (handlers.py:301). The forwarder runs
de-anonymization first, then this swap (`forwarder.py:192-205`), so a Sabre session-reuse request
gets its `BinarySecurityToken` decrypted and then overwritten by a fresh `UsernameToken`.

Observed SOAP-session behavior:
- Sabre session-creation requests use a `UsernameToken`; later session-reuse requests carry only a
  `BinarySecurityToken` inside `<Security>`.
- Amadeus start/stateless requests use a digest `UsernameToken`; stateful follow-up requests carry
  `awsse:Session` metadata outside `<Security>`, and `SequenceNumber` must remain plaintext and
  numeric for the caller.

Deployment: customer runs the proxy with real GDS credentials; Wenrix sends fake credentials.

## Goals / Non-Goals

**Goals:**
- Sabre session reuse works end-to-end through the relay (no per-request new session).
- Amadeus stateful sessions survive the relay (`SequenceNumber` remains an integer for the client).
- Swap-enabled channels are validated for credentials at config load (fail fast).
- Fake credentials never reach the supplier; real credentials never returned to Wenrix.

**Non-Goals:**
- Relay-side session lifecycle management (relay stays stateless: encrypt-on-response /
  decrypt-on-request only).
- Changes to non-SOAP handlers (Travelfusion/NDC/Farelogix) beyond the shared validation hook default.
- Operation-name-based gating (rejected in favor of content-based gating).

## Decisions

**1. Content-based gating (not operation-name).** In `swap_request_body`, locate the security target;
if it contains a `BinarySecurityToken` (local name), return `False` (skip — de-anon already restored
the real token). Otherwise build and replace the fragment as today. This mirrors the supplier's own
either/or model, is stateless, and handles Sabre, Amadeus, and Sabre-sessionless uniformly.
- Add `_contains_binary_security_token(target)` scanning the target subtree by local name.
- Change target resolution to an optional form: return `None` (skip) when the `<Security>` element or
  a valid xpath match is simply absent; still raise `CredentialSwapError` for an *invalid xpath
  expression* (a config bug). `swap_request_body` returns `False` on `None`.

**2. Amadeus response-auth set = `{SessionId, SecurityToken}`.** Remove `SequenceNumber` from
`AmadeusHandler.response_auth_local_names` (handlers.py:361). `SecurityToken` (auth) and `SessionId`
stay encrypted and round-trip opaquely via de-anon; `SequenceNumber` stays plaintext so the client
can parse/increment it. Sabre set stays `{BinarySecurityToken}`.

**3. Config-load validation via a handler hook.** Add `validate_credentials(channel) -> None` to the
`ChannelHandler` protocol (`base.py`) with a no-op default mixin. `SoapSecurityHandler` requires
`soap_security` XOR (`soap_username` and `soap_password`) when `channel.credential_swap_enabled`,
raising a config error naming the channel otherwise. Invoke from the config loader
(`src/channel_relay/config/`) after channels are built — not from `config/models.py` — to avoid a
`config → channels` import cycle (channels already imports `config.models`).

**4. Fail-closed invariant preserved.** A present `UsernameToken` is always swapped or errors; skip
happens only for `BinarySecurityToken`/absent-`Security` cases, where no fake `UsernameToken` exists
to leak.

## Risks / Trade-offs

- **Existing test asserts the old (wrong) behavior.** `test_encrypted_token_round_trips_on_next_request`
  (`tests/integration/test_pii_sabre_relay.py:120`) asserts the static `>RELAY<` fragment reaches the
  channel on reuse. It must be rewritten to assert the de-anonymized `BinarySecurityToken` reaches the
  channel and no `UsernameToken` is injected. `test_amadeus_*` SequenceNumber assertions likewise flip.
- **Detection is by local name.** A malformed/renamed session token element would be treated as
  "no session token" → the swap would inject a `UsernameToken`, creating a new session rather than
  silently leaking — acceptable (fails safe upstream, no credential exposure).
- **Absent-Security becomes a no-op instead of 502.** A genuinely malformed request that should carry a
  `UsernameToken` but has no `Security` now forwards without credentials and is rejected by the
  supplier rather than by the relay. No credential leak; the mis-shaped request simply fails upstream.
