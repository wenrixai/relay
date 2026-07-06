# channel-credential-swap Specification

## Purpose
TBD - created by archiving change slice-3-channel-credential-swap. Update Purpose after archive.
## Requirements
### Requirement: Channel handler registry

The relay SHALL provide a channel handler registry keyed by `ChannelType`. Each handler SHALL expose
body-derived operation parsing plus request and response swap hooks. If a channel has no configured
credentials, credential swap SHALL be a no-op.

#### Scenario: Handler resolved by channel type
- **WHEN** a configured channel is forwarded
- **THEN** the relay uses the handler registered for that channel's `type`

#### Scenario: Empty credentials preserve pass-through
- **WHEN** a channel has no credentials
- **THEN** the channel handler does not mutate the request body or supplier credential headers

### Requirement: Body-derived operation parsing

The relay SHALL parse operation names from the XML request body using the selected channel handler
and SHALL NOT use client-supplied headers as the source of operation names.

#### Scenario: SOAP operation parsed from body
- **WHEN** a SOAP body contains a first operation element
- **THEN** Amadeus, Sabre, and Travelport parse that element local-name as the operation

#### Scenario: Header ignored
- **WHEN** a request header claims a different operation than the XML body
- **THEN** the body-derived operation is used

### Requirement: Per-channel request credential swap

For configured credentials, the relay SHALL structurally replace only the configured
channel-specific credential locations before forwarding.

For an Amadeus, Sabre, or Travelport channel the SOAP `Security` header is replaced either with a
static configured `soap_security` fragment (default) or, when `soap_username` is configured, with a
dynamically built WS-Security `UsernameToken` regenerated per request. The dynamic fragment carries a
fresh `Nonce` (16 random bytes, Base64) and `Created` (current UTC, ISO-8601 `...Z`); its `Password`
follows `soap_password_type`: `digest` (default) → `Base64(SHA1(nonce ‖ created ‖ SHA1(password)))`
with `Type=…#PasswordDigest` (Amadeus WSAP variant), or `text` → plaintext with `Type=…#PasswordText`.
Namespaces default to the OASIS 2004 `wsse`/`wsu` URIs, overridable via `soap_wsse_ns`/`soap_wsu_ns`.
An invalid `soap_password_type` SHALL fail closed. Password and key material SHALL never be logged.

#### Scenario: Travelfusion request credentials swapped
- **WHEN** a Travelfusion request contains operation `LoginId` and `XmlLoginId`
- **THEN** those elements are replaced from configured credentials

#### Scenario: NDC header credentials swapped
- **WHEN** BA or LA NDC credentials are configured
- **THEN** the relay adds the channel-specific outbound API key header and leaves the body unchanged

#### Scenario: Farelogix XML attributes swapped
- **WHEN** Farelogix credentials are configured and the request contains `tc/iden` and `tc/agent`
- **THEN** the relay replaces only the configured credential attributes and subscription header

#### Scenario: SOAP security header replaced
- **WHEN** Amadeus, Sabre, or Travelport `soap_security` is configured and no `soap_username` is set
- **THEN** the relay replaces the configured SOAP security header structurally with that XML fragment

#### Scenario: Dynamic UsernameToken per request
- **WHEN** a channel configures `soap_username` and `soap_password` in digest mode
- **THEN** each forwarded request carries a `Security` `UsernameToken` with a fresh `Nonce`, `Created`,
  and `PasswordDigest` computed as `Base64(SHA1(nonce ‖ created ‖ SHA1(password)))`

#### Scenario: Fresh values across requests
- **WHEN** two requests are swapped for the same dynamic channel
- **THEN** their `Nonce` and `Created` values differ

#### Scenario: Text password mode
- **WHEN** `soap_password_type` is `text`
- **THEN** the `Password` element carries the plaintext password with `Type=…#PasswordText` and a fresh
  `Nonce`/`Created`

### Requirement: Channel response credential cleanup

The relay SHALL apply channel response credential cleanup before normal PII redaction.

For a credentialed Amadeus or Sabre channel, response authentication fields are replaced with `ENC_`
tokens independent of `pii.enabled`. Because these encrypted session tokens are returned to the
client and replayed on subsequent requests, the relay SHALL de-anonymize (decrypt) encrypted tokens
on the request path whenever response-auth encryption is active for the channel — that is, whenever
the channel's handler requires a response keyring — even when `pii.enabled` is false, so token
encryption (response) and decryption (request) stay symmetric for the credential-swap-only
configuration and a replayed session token is restored to plaintext before the channel receives it.

#### Scenario: Travelfusion login fields stripped
- **WHEN** Travelfusion credentials are configured and a response contains login credential fields
- **THEN** the relay removes those fields before returning the response

#### Scenario: Sabre and Amadeus response auth encrypted
- **WHEN** Sabre or Amadeus credentials are configured and response authentication fields are present
- **THEN** those values are replaced with `ENC_` tokens generated by the configured PII keyring

#### Scenario: Response session token encrypted without PII enabled
- **WHEN** a credentialed Sabre or Amadeus channel with `pii.enabled=false` returns a session auth field
- **THEN** the client receives that value as an `ENC_` token

#### Scenario: Replayed session token decrypted without PII enabled
- **WHEN** the client sends a subsequent request to that channel carrying the `ENC_` session token
- **THEN** the relay decrypts it to plaintext before forwarding, and no `ENC_` token reaches the channel

### Requirement: Credential swap failure handling

The relay SHALL fail closed with HTTP 502 and reason `credential_swap_failed` when credential swap is
required but the expected credential XML structure is missing or malformed.

#### Scenario: Missing required swap target fails closed
- **WHEN** configured credentials require a missing XML target
- **THEN** the request is not forwarded and the client receives `credential_swap_failed`
