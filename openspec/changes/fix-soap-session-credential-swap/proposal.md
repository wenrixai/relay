## Why

The generic SOAP credential swap replaces the entire `<Security>` element on **every** credentialed
request. This is fatal for Sabre's real two-phase session model: after `SessionCreateRQ`, Sabre
carries the session as a `BinarySecurityToken` **inside** `<Security>` on every subsequent request.
The relay de-anonymizes that token, then immediately discards it and injects a fresh `UsernameToken`,
so Sabre opens a new session per request → session-pool exhaustion (`MaximumTokensFault`). Amadeus is
unaffected only because its session lives **outside** `<Security>` (in `awsse:Session`). Separately,
the relay encrypts Amadeus `SequenceNumber`, which the real client parses as an integer and
increments — an `ENC_` value breaks it. Finally, a swap-enabled channel with no configured
credentials fails only at first request, not at config load.

Deployment context: the customer runs the proxy holding the **real** GDS credentials; Wenrix sends
**fake/placeholder** credentials and must never learn the real ones.

## What Changes

- **Content-gate the SOAP request swap.** Replace SOAP credentials only when the security target
  carries a `UsernameToken` (or placeholder). When it carries a `BinarySecurityToken` (session
  reuse), the relay leaves the de-anonymized token intact and does **not** re-credential the request.
  A request with no `<Security>` element (e.g. Amadeus stateful non-start) is likewise left alone.
- **Keep Amadeus `SequenceNumber` plaintext.** Response-auth encryption for Amadeus covers
  `SessionId` and `SecurityToken` only; `SequenceNumber` is never encrypted so the client can parse
  and increment it. Sabre continues to encrypt `BinarySecurityToken`.
- **Validate credentials at config load.** A channel with credential swap enabled MUST have SOAP auth
  configured (`soap_security` XOR `soap_username`+`soap_password`); otherwise config load fails with a
  clear error instead of a per-request 502.
- Fake credentials are still never forwarded to the supplier: a present `UsernameToken` is always
  swapped or the request fails closed.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `channel-credential-swap`: request swap becomes content-gated (skip session-reuse requests carrying
  a `BinarySecurityToken`); Amadeus response-auth encryption excludes `SequenceNumber`; swap-enabled
  channels are validated for configured credentials at config load.

## Impact

- Code: `src/channel_relay/channels/handlers.py` (`SoapSecurityHandler.swap_request_body`,
  `_security_target`, `AmadeusHandler.response_auth_local_names`, new SOAP `validate_credentials`),
  `src/channel_relay/channels/base.py` (protocol hook + default), `src/channel_relay/config/` loader
  (invoke validation at load).
- Tests: `tests/integration/test_pii_sabre_relay.py` (session-reuse assertion is currently inverted
  and must be rewritten), `tests/integration/test_session_deanon_gate.py`,
  `tests/unit/test_channel_handlers.py`, `tests/unit/test_channel_credential_swap.py`, config loader
  tests.
- No new dependencies. No `WP_*` compatibility impact. Behavior change is limited to SOAP channels
  with credential swap enabled.
