## 1. Failing tests first (TDD)

- [x] 1.1 Rewrite `test_encrypted_token_round_trips_on_next_request` (tests/integration/test_pii_sabre_relay.py) to assert that on a Sabre reuse request carrying an `ENC_` `BinarySecurityToken`, the de-anonymized real token reaches the channel and NO `UsernameToken`/`soap_security` fragment is injected (no `>RELAY<`, no `ENC_`).
- [x] 1.2 Add unit test: Sabre request whose `<Security>` contains a `BinarySecurityToken` → `swap_request_body` returns `False` and leaves the element unchanged (tests/unit/test_channel_handlers.py or test_channel_credential_swap.py).
- [x] 1.3 Add unit test: Sabre `SessionCreateRQ` with a fake `UsernameToken` → swapped to the configured `soap_security` (confirm auth path still works).
- [x] 1.4 Add unit test: credentialed SOAP request with no `<Security>` element → `swap_request_body` returns `False` (no-op, no error).
- [x] 1.5 Update Amadeus response tests (test_channel_handlers.py `test_amadeus_encrypts_session_tokens_in_response`; test_session_deanon_gate.py) to assert `SessionId`/`SecurityToken` → `ENC_` while `SequenceNumber` stays plaintext.
- [x] 1.6 Add config-load test: SOAP channel with `credentials.enabled=true` and neither `soap_security` nor `soap_username`+`soap_password` → load raises a clear error naming the channel; a validly configured channel loads.
- [x] 1.7 Add no-leak regression test: no configured real-credential string appears in any response body/headers returned to the client.

## 2. Content-gated SOAP request swap

- [x] 2.1 Add `_contains_binary_security_token(target)` helper in handlers.py (scan subtree by local name `BinarySecurityToken`).
- [x] 2.2 Split `_security_target` into an optional resolver that returns `None` when `<Security>`/xpath match is absent, but still raises `CredentialSwapError` for an invalid xpath expression.
- [x] 2.3 Update `SoapSecurityHandler.swap_request_body`: return `False` when target is `None` or contains a `BinarySecurityToken`; otherwise build/replace the fragment as today.

## 3. Amadeus SequenceNumber plaintext

- [x] 3.1 Change `AmadeusHandler.response_auth_local_names` to `{"SessionId", "SecurityToken"}` (drop `SequenceNumber`).

## 4. Config-load credential validation

- [x] 4.1 Add `validate_credentials(self, channel) -> None` to the `ChannelHandler` protocol and a no-op default mixin in channels/base.py.
- [x] 4.2 Implement `SoapSecurityHandler.validate_credentials`: when `credential_swap_enabled`, require `soap_security` XOR (`soap_username` and `soap_password`); else raise a clear config error.
- [x] 4.3 Invoke validation in the config loader (src/channel_relay/config/) after channels are built, iterating channels; failure aborts load with a message naming the channel.

## 5. Verify

- [x] 5.1 Run targeted suites green (`uv run pytest tests/integration/test_pii_sabre_relay.py tests/integration/test_session_deanon_gate.py tests/unit/test_channel_handlers.py tests/unit/test_channel_credential_swap.py --junitxml=...`).
- [x] 5.2 `openspec validate fix-soap-session-credential-swap --strict`.
- [x] 5.3 `just ci` green (lint + fmt + types + pylint + full test).
