## MODIFIED Requirements

### Requirement: Per-channel request credential swap

For explicitly enabled configured credentials, the relay SHALL structurally replace only the
configured channel-specific credential locations before forwarding.

For an Amadeus, Sabre, or Travelport channel the SOAP `Security` header is replaced either with a
static configured `soap_security` fragment (default) or, when `soap_username` is configured, with a
dynamically built WS-Security `UsernameToken` regenerated per request. The dynamic fragment carries a
fresh `Nonce` (16 random bytes, Base64) and `Created` (current UTC, ISO-8601 `...Z`); its `Password`
follows `soap_password_type`: `digest` (default) → `Base64(SHA1(nonce ‖ created ‖ SHA1(password)))`
with `Type=…#PasswordDigest` (Amadeus WSAP variant), or `text` → plaintext with `Type=…#PasswordText`.
Namespaces default to the OASIS 2004 `wsse`/`wsu` URIs, overridable via `soap_wsse_ns`/`soap_wsu_ns`.
An invalid `soap_password_type` SHALL fail closed. Password and key material SHALL never be logged.

The SOAP `Security` replacement SHALL be content-gated so a stateful session request is not
re-credentialed. The relay SHALL replace the SOAP security header only when its security target
carries a `UsernameToken` (the fake placeholder credential). WHERE the security target instead
carries a `BinarySecurityToken` — a session-reuse request whose token was already restored to
plaintext by request de-anonymization — the relay SHALL leave that target unchanged and forward the
de-anonymized token. WHERE no SOAP `Security` element is present at all (for example an Amadeus
stateful non-start request whose session lives outside `Security`), the SOAP swap SHALL be a no-op
for that request. A fake `UsernameToken` present in the request SHALL always be replaced with real
credentials or the request SHALL fail closed; a placeholder credential SHALL never reach the supplier.

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
- **WHEN** Amadeus, Sabre, or Travelport `soap_security` is configured with
  `credentials.enabled=true` and no `soap_username` is set and the request `Security` carries a
  `UsernameToken`
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

#### Scenario: Session-reuse request is not re-credentialed
- **WHEN** a Sabre request's `Security` header carries a `BinarySecurityToken` (already de-anonymized
  to plaintext on the request path) rather than a `UsernameToken`
- **THEN** the relay leaves the `Security` header unchanged, forwards the de-anonymized token, and does
  not inject a `UsernameToken` or the static `soap_security` fragment

#### Scenario: Request without a SOAP Security header is untouched
- **WHEN** a credentialed SOAP request has no `Security` element (for example an Amadeus stateful
  non-start request whose session lives in `awsse:Session` outside `Security`)
- **THEN** the SOAP credential swap makes no change to that request

### Requirement: Channel response credential cleanup

The relay SHALL apply channel response credential cleanup before normal PII redaction.

For a credentialed Amadeus or Sabre channel, response authentication fields are replaced with `ENC_`
tokens independent of `pii.enabled`. Because these encrypted session tokens are returned to the
client and replayed on subsequent requests, the relay SHALL de-anonymize (decrypt) encrypted tokens
on the request path whenever response-auth encryption is active for the channel — that is, whenever
the channel's handler requires a response keyring — even when `pii.enabled` is false, so token
encryption (response) and decryption (request) stay symmetric for the credential-swap-only
configuration and a replayed session token is restored to plaintext before the channel receives it.

For a Sabre channel the encrypted response-auth field SHALL be `BinarySecurityToken`. For an Amadeus
channel the encrypted response-auth fields SHALL be `SessionId` and `SecurityToken` only; `SequenceNumber`
SHALL NOT be encrypted, because it is a non-secret conversation counter the client parses as an integer
and increments — encrypting it would break session continuity.

#### Scenario: Travelfusion login fields stripped
- **WHEN** Travelfusion credentials are configured with `credentials.enabled=true` and a response
  contains login credential fields
- **THEN** the relay removes those fields before returning the response

#### Scenario: Sabre and Amadeus response auth encrypted
- **WHEN** Sabre or Amadeus credentials are configured with `credentials.enabled=true` and response
  authentication fields are present
- **THEN** those values are replaced with `ENC_` tokens generated by the configured PII keyring

#### Scenario: Amadeus SequenceNumber left plaintext
- **WHEN** a credentialed Amadeus response contains `SessionId`, `SequenceNumber`, and `SecurityToken`
- **THEN** `SessionId` and `SecurityToken` are replaced with `ENC_` tokens and `SequenceNumber` is
  returned to the client unchanged (plaintext)

#### Scenario: Response session token encrypted without PII enabled
- **WHEN** a credentialed Sabre or Amadeus channel with `pii.enabled=false` returns a session auth field
- **THEN** the client receives that value as an `ENC_` token

#### Scenario: Replayed session token decrypted without PII enabled
- **WHEN** the client sends a subsequent request to that channel carrying the `ENC_` session token
- **THEN** the relay decrypts it to plaintext before forwarding, and no `ENC_` token reaches the channel

## ADDED Requirements

### Requirement: Credential configuration validated at load

WHEN a channel has credential swap enabled, the relay SHALL validate at configuration load time that
the channel has the credential material its handler requires, and SHALL abort startup with a clear
error naming the channel when it does not. For an Amadeus, Sabre, or Travelport SOAP channel the
required material is either a static `soap_security` fragment or the dynamic pair `soap_username` and
`soap_password` (exactly one of the two forms). This validation replaces first-request failure for the
missing-configuration case; runtime fail-closed handling still applies to other swap errors.

#### Scenario: SOAP channel missing credential material fails config load
- **WHEN** an Amadeus, Sabre, or Travelport channel sets `credentials.enabled=true` but configures
  neither `soap_security` nor `soap_username`+`soap_password`
- **THEN** configuration load fails with an error identifying the channel, and the relay does not start

#### Scenario: Validly configured SOAP channel loads
- **WHEN** a SOAP channel with credential swap enabled configures `soap_security` (or
  `soap_username`+`soap_password`)
- **THEN** configuration load succeeds
