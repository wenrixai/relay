## Why

The SOAP credential swap replaces the request `Security` header with a **static** `soap_security`
XML fragment from config. That works for stateful session-create with a plaintext password, but it
cannot satisfy **Amadeus stateless WS-Security**, whose `UsernameToken` requires a **fresh
per-request** `Nonce`, `Created` timestamp, and `PasswordDigest`. A frozen fragment carries stale
values and Amadeus rejects it once the timestamp falls outside its acceptance window.

## What Changes

- Add an **opt-in dynamic UsernameToken** mode to the SOAP security handler. When a channel's
  credentials include `soap_username`, the relay builds the `Security` fragment fresh on every
  request instead of using the static `soap_security` fragment:
  - `Nonce` = 16 random bytes (Base64-encoded), regenerated per request.
  - `Created` = current UTC timestamp, ISO-8601 `...Z`, per request.
  - `Password` per `soap_password_type`:
    - `digest` (default): `PasswordDigest = Base64( SHA1( nonce ‖ created ‖ SHA1(password) ) )` —
      the **Amadeus WSAP variant** (inner `SHA1(password)`, not plaintext).
    - `text`: `PasswordText` = the plaintext password, still with a fresh `Nonce`/`Created`.
  - WS-Security namespaces default to the OASIS 2004 `wsse`/`wsu` URIs, overridable via
    `soap_wsse_ns` / `soap_wsu_ns`.
- The static-fragment path is unchanged and remains the default when `soap_username` is absent. As
  today, an existing `Security` element must be present as the replacement target; if absent the swap
  fails closed (502 `credential_swap_failed`).
- New credential keys (all optional; `credentials` is a free-form `dict[str, str]`, so no config
  schema change): `soap_username`, `soap_password`, `soap_password_type`, `soap_wsse_ns`,
  `soap_wsu_ns`.

### Security note

The SHA-1 used here is **mandated by the WS-Security UsernameToken profile**; it is a protocol
digest, not a change to the relay's field crypto (AES-256-CTR / HKDF keyring), which is untouched.
No password or key material is logged. Fragments are assembled with lxml (proper escaping) and
re-validated through the hardened parser before insertion.

## Capabilities

### Modified Capabilities
- `channel-credential-swap`: the SOAP security header MAY be built dynamically as a WS-Security
  `UsernameToken` with a fresh per-request `Nonce`/`Created`/`PasswordDigest` when `soap_username` is
  configured, enabling Amadeus stateless authentication; otherwise the static fragment is used.

## Impact

- `src/channel_relay/channels/wsse.py` (new): `password_digest(...)` and
  `build_username_token_security(...)`, unit-testable in isolation.
- `src/channel_relay/channels/handlers.py`: `SoapSecurityHandler.swap_request_body` selects the
  dynamic builder when `soap_username` is present; new `_dynamic_security_fragment` helper generates
  the nonce/timestamp per request.
- Tests: `tests/unit/test_wsse.py` (digest vector + both password types),
  `tests/unit/test_channel_credential_swap.py` (dynamic vs static selection, fresh nonce), and an
  integration round-trip.
