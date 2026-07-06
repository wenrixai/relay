## 1. WS-Security builder

- [x] 1.1 `tests/unit/test_wsse.py`: `password_digest` matches the Amadeus variant
      `Base64(SHA1(nonce ‖ created ‖ SHA1(password)))` for a fixed vector; `build_username_token_security`
      (digest) yields `Username`, `Password Type=…#PasswordDigest` with a recomputable digest,
      Base64 `Nonce`, and `Created`; text mode yields `PasswordText` = plaintext; username escaped
- [x] 1.2 `src/channel_relay/channels/wsse.py`: `password_digest(...)` +
      `build_username_token_security(...)` (lxml-built, escaped), OASIS-2004 default namespaces and
      profile type URIs

## 2. Handler wiring

- [x] 2.1 `tests/unit/test_channel_credential_swap.py`: Amadeus with `soap_username` builds a dynamic
      UsernameToken (no static `soap_security` needed); two swaps produce different Nonce; static
      fragment still used when `soap_username` absent; invalid `soap_password_type` →
      `CredentialSwapError`
- [x] 2.2 `src/channel_relay/channels/handlers.py`: `SoapSecurityHandler.swap_request_body` uses
      `_dynamic_security_fragment(credentials)` when `soap_username` present, else the static
      fragment; `_dynamic_security_fragment` generates `os.urandom` nonce + UTC `Created`

## 3. Integration

- [x] 3.1 `tests/integration/test_amadeus_wsse_dynamic.py`: forwarded request's `Security` carries a
      fresh UsernameToken digest recomputable from the emitted Nonce+Created; client credentials do
      not leak upstream

## 4. Verification

- [x] 4.1 `just test-fast` green
- [x] 4.2 `just ci` green — 359 passed, 95% coverage
