# channel-credential-swap Specification

## Purpose
TBD - created by archiving change slice-3-channel-credential-swap. Update Purpose after archive.
## Requirements
### Requirement: Channel handler registry

The relay SHALL provide a channel handler registry keyed by `ChannelType`. Each handler SHALL expose
body-derived operation parsing plus request and response swap hooks. Credential swap SHALL run only
when `credentials.enabled` is explicitly true. If a channel has no enabled credentials, credential
swap SHALL be a no-op.

#### Scenario: Handler resolved by channel type
- **WHEN** a configured channel is forwarded
- **THEN** the relay uses the handler registered for that channel's `type`

#### Scenario: Disabled credentials preserve pass-through
- **WHEN** a channel omits `credentials.enabled` or sets it to false
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

For explicitly enabled configured credentials, the relay SHALL structurally replace only the
configured channel-specific credential locations before forwarding.

For an Amadeus or Sabre channel the SOAP `Security` header is replaced either with a static
configured `soap_security` fragment (default) or, when `soap_username` is configured, with a
dynamically built WS-Security `UsernameToken` regenerated per request. The dynamic fragment carries a
fresh `Nonce` (16 random bytes, Base64) and `Created` (current UTC, ISO-8601 `...Z`); its `Password`
follows `soap_password_type`: `digest` (default) →
`Base64(SHA1(nonce ‖ created ‖ SHA1(password)))` with `Type=…#PasswordDigest` (Amadeus WSAP variant),
or `text` → plaintext with `Type=…#PasswordText`. Namespaces default to the OASIS 2004 `wsse`/`wsu`
URIs, overridable via `soap_wsse_ns`/`soap_wsu_ns`. An invalid `soap_password_type` SHALL fail
closed. Password and key material SHALL never be logged.

For a Travelport Universal API channel, the relay SHALL replace every case variant of the inbound
`Authorization` header with exactly one outbound standard HTTP Basic header. The encoded credential
string SHALL be `Universal API/<username>:<password>`, where `username` and `password` come from the
enabled channel credential configuration and the relay adds the required `Universal API/` prefix.
Travelport authentication SHALL NOT add, replace, or remove SOAP body/header elements.

#### Scenario: Travelfusion request credentials swapped
- **WHEN** a Travelfusion request contains operation `LoginId` and `XmlLoginId` and
  `credentials.enabled=true`
- **THEN** those elements are replaced from configured credentials

#### Scenario: NDC header credentials swapped
- **WHEN** BA or LA NDC credentials are configured with `credentials.enabled=true`
- **THEN** the relay adds the channel-specific outbound API key header and leaves the body unchanged

#### Scenario: Farelogix XML attributes swapped
- **WHEN** Farelogix credentials are configured with `credentials.enabled=true` and the request
  contains `tc/iden` and `tc/agent`
- **THEN** the relay replaces only the configured credential attributes and subscription header

#### Scenario: SOAP security header replaced
- **WHEN** Amadeus or Sabre `soap_security` is configured with `credentials.enabled=true` and no
  `soap_username` is set
- **THEN** the relay replaces the configured SOAP security header structurally with that XML fragment

#### Scenario: Dynamic UsernameToken per request
- **WHEN** an Amadeus or Sabre channel configures `soap_username` and `soap_password` in digest mode
- **THEN** each forwarded request carries a `Security` `UsernameToken` with a fresh `Nonce`, `Created`,
  and `PasswordDigest` computed as `Base64(SHA1(nonce ‖ created ‖ SHA1(password)))`

#### Scenario: Fresh values across requests
- **WHEN** two Amadeus or Sabre requests are swapped for the same dynamic channel
- **THEN** their `Nonce` and `Created` values differ

#### Scenario: Text password mode
- **WHEN** an Amadeus or Sabre channel's `soap_password_type` is `text`
- **THEN** the `Password` element carries the plaintext password with `Type=…#PasswordText` and a fresh
  `Nonce`/`Created`

#### Scenario: Travelport Basic authorization replaces caller value
- **WHEN** a Travelport request has enabled `username` and `password` credentials and carries any
  caller-supplied case variant of `Authorization`
- **THEN** the channel receives exactly one `Authorization` header equal to Basic encoding of
  `Universal API/<username>:<password>` and no caller credential value

#### Scenario: Travelport stateless SOAP body is not credential-swapped
- **WHEN** an enabled Travelport channel forwards a stateless SOAP request
- **THEN** authentication changes only the outbound `Authorization` header and does not insert or
  replace a SOAP `Security` element

#### Scenario: Travelport session context is preserved
- **WHEN** an enabled Travelport channel forwards a sessioned SOAP request containing
  `SessionContext/SessTok/@id` and an operation `@SessionKey`
- **THEN** both session values reach Travelport unchanged after any required token de-anonymization

### Requirement: Channel response credential cleanup

The relay SHALL apply channel response credential cleanup before normal PII redaction.

For a credentialed Amadeus, Sabre, or Travelport channel, response authentication fields are replaced
with `ENC_` tokens independent of `pii.enabled`. Because these encrypted session tokens are returned
to the client and replayed on subsequent requests, the relay SHALL de-anonymize (decrypt) encrypted
tokens on the request path whenever response-auth encryption is active for the channel — that is,
whenever the channel's handler requires a response keyring — even when `pii.enabled` is false, so
token encryption (response) and decryption (request) stay symmetric for the credential-swap-only
configuration and a replayed session token is restored to plaintext before the channel receives it.

For Travelport, response authentication fields SHALL include every `SessionKey` attribute and an
`id` attribute only when its owning element local-name is `SessTok`. Cleanup SHALL leave an already
encrypted token unchanged and SHALL fail closed rather than return a plaintext session key when a
required keyring or encryption operation is unavailable.

#### Scenario: Travelfusion login fields stripped
- **WHEN** Travelfusion credentials are configured with `credentials.enabled=true` and a response
  contains login credential fields
- **THEN** the relay removes those fields before returning the response

#### Scenario: Sabre and Amadeus response auth encrypted
- **WHEN** Sabre or Amadeus credentials are configured with `credentials.enabled=true` and response
  authentication fields are present
- **THEN** those values are replaced with `ENC_` tokens generated by the configured PII keyring

#### Scenario: Response session token encrypted without PII enabled
- **WHEN** a credentialed Amadeus, Sabre, or Travelport channel with `pii.enabled=false` returns a
  response authentication field
- **THEN** the client receives that value as an `ENC_` token

#### Scenario: Replayed session token decrypted without PII enabled
- **WHEN** the client sends a subsequent request to that channel carrying the `ENC_` session token
- **THEN** the relay decrypts it to plaintext before forwarding, and no `ENC_` token reaches the channel

#### Scenario: Travelport Booking Start session key protected
- **WHEN** an enabled Travelport channel returns `BookingStartRsp` with a plaintext `SessionKey`
  attribute
- **THEN** the client receives an `ENC_` value and never receives the plaintext session key

#### Scenario: Travelport repeated session key restored
- **WHEN** a later Travelport request repeats the returned `ENC_` value in both `SessTok/@id` and the
  operation's `SessionKey` attribute
- **THEN** Travelport receives the original plaintext value in both locations

#### Scenario: Unrelated Travelport IDs are not encrypted
- **WHEN** a Travelport response contains `id` attributes outside a `SessTok` element
- **THEN** response credential cleanup leaves those unrelated attributes unchanged

### Requirement: Travelport credential configuration validation

When Travelport credential swap is enabled, the relay SHALL validate at configuration load that
non-empty `username` and `password` values are present, the username does not contain `:`, neither
value contains control characters, and obsolete Travelport SOAP credential keys are absent.
Validation SHALL abort startup with an error that identifies the channel and invalid condition but
does not contain any credential value.

#### Scenario: Complete Travelport credentials accepted
- **WHEN** an enabled Travelport channel configures valid `username` and `password` values
- **THEN** configuration loading succeeds

#### Scenario: Incomplete Travelport credentials rejected
- **WHEN** an enabled Travelport channel omits either `username` or `password`
- **THEN** configuration loading aborts before the relay accepts traffic

#### Scenario: Obsolete Travelport SOAP credentials rejected
- **WHEN** an enabled Travelport channel configures `soap_security`, `soap_username`, or
  `soap_password`
- **THEN** configuration loading aborts with migration-safe detail that names no credential value

#### Scenario: Disabled Travelport swap needs no credentials
- **WHEN** a Travelport channel has `credentials.enabled=false`
- **THEN** configuration loading does not require Travelport `username` or `password`

### Requirement: Credential swap failure handling

The relay SHALL fail closed with HTTP 502 and reason `credential_swap_failed` when credential swap is
required but the expected credential XML structure is missing or malformed.

#### Scenario: Missing required swap target fails closed
- **WHEN** configured credentials require a missing XML target
- **THEN** the request is not forwarded and the client receives `credential_swap_failed`

### Requirement: Credential configuration validation for all swap-enabled channels
When credential swap is enabled for a channel, the relay SHALL validate at configuration load that the
credential fields its handler requires are present and well-formed, for **every** channel type that
performs a swap — Travelfusion, Farelogix (AA/LH/UA/EK), the NDC header channels (BA/LA), and the SOAP
(Amadeus/Sabre) and Travelport channels. Validation failure SHALL abort startup with an error that
identifies the channel and the invalid condition and contains no credential value. A channel with
`credentials.enabled=false` SHALL require no credentials.

This generalizes the existing Travelport/SOAP load-time validation to the remaining swap handlers, so
that an incomplete credential set can never boot ready and then fail every request at swap time with
`credential_swap_failed`.

#### Scenario: Incomplete Farelogix credentials rejected at load
- **WHEN** an enabled Farelogix channel omits a required field (e.g. `password` or an agent field)
- **THEN** configuration loading aborts before the relay accepts traffic, naming the channel

#### Scenario: Missing NDC API key rejected at load
- **WHEN** an enabled BA/LA NDC channel omits its required API-key credential
- **THEN** configuration loading aborts before the relay accepts traffic, naming the channel

#### Scenario: Incomplete Travelfusion credentials rejected at load
- **WHEN** an enabled Travelfusion channel omits a required login field
- **THEN** configuration loading aborts before the relay accepts traffic, naming the channel

#### Scenario: Disabled swap needs no credentials
- **WHEN** a swap-capable channel has `credentials.enabled=false`
- **THEN** configuration loading does not require its credential fields

