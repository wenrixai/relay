## MODIFIED Requirements

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
