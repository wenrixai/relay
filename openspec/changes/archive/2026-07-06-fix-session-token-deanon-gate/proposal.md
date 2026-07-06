## Why

Response auth encryption and request de-anonymization are gated asymmetrically for credentialed
Sabre/Amadeus channels.

- **Response:** `SoapSecurityHandler.swap_response` encrypts session auth fields
  (`BinarySecurityToken` / `SessionId` / `SecurityToken` / …) into `ENC_` tokens whenever
  `requires_response_keyring(channel)` is true — i.e. an Amadeus/Sabre channel with credentials,
  **independent of `pii.enabled`**.
- **Request:** de-anonymization only runs when `need_pii = channel.pii.enabled and keyring and XML`.

So a channel configured with `credentials` but `pii.enabled = false` (the default) will hand the
client an `ENC_`-wrapped session token in the response, then **never decrypt it** when the client
sends it back on the next request — the `ENC_` token reaches the channel and upstream rejects the
session. Session continuation is silently broken for the credential-swap-only configuration.

The credential-swap feature is enabled by the presence of channel `credentials` (empty by default =
off). The response side already keys off that; this change makes the request side match, so token
encrypt/decrypt is symmetric whenever credential swap is enabled.

## What Changes

- `forwarder.forward()` SHALL run request de-anonymization when **either** PII is enabled **or** the
  channel's handler requires a response keyring (credential-swap session-token encryption is active),
  for an XML request body with a keyring present.
- No change to `deanonymize_request_body` (it already decrypts every valid `ENC_` token regardless of
  PII rules), and no startup change (`build_keyring` already forces a keyring for credentialed
  Sabre/Amadeus via `credentials_require_response_keyring`).

## Capabilities

### Modified Capabilities
- `channel-credential-swap`: request de-anonymization of encrypted session tokens SHALL occur
  whenever response-auth encryption is active for the channel (credential swap enabled), not only
  when `pii.enabled` is true, so encrypted session tokens round-trip symmetrically.

## Impact

- `src/channel_relay/proxy/forwarder.py`: add `need_session_deanon` (from
  `handler.requires_response_keyring(channel)`); enter the request body block and run the
  de-anonymization stage on `need_pii or need_session_deanon`.
- Tests: `tests/integration/test_pii_sabre_relay.py` (or a sibling) — a credentialed Sabre channel
  with `pii.enabled=false` round-trips the session token with no `ENC_` reaching the channel.
