## Context

Travelport Universal API uses SOAP/XML as its message format but authenticates each HTTPS request at
the HTTP layer. Its documented credential form is standard Basic authentication over the UTF-8/ASCII
credential string `Universal API/<username>:<password>`. The current `TravelportHandler` subclasses
`SoapSecurityHandler`, so it mutates a SOAP `Security` element and does not replace the caller's
`Authorization` header.

Travelport sessioning is a separate protocol concern. `BookingStartRsp` returns a `SessionKey`;
follow-up requests repeat it as `SessionContext/SessTok/@id` and as the operation's `SessionKey`
attribute. Those values identify a supplier-side workspace and must round-trip without the relay
owning session lifecycle. The existing forwarder already provides the required ordering:
header hygiene, credential-header swap, request token de-anonymization, upstream call, response
credential cleanup, then PII redaction.

The design must retain hardened XML parsing, fail closed before upstream forwarding, avoid body or
credential logging, perform no live network calls in tests, and add no retry behavior.

## Goals / Non-Goals

**Goals:**

- Emit exactly one Travelport `Authorization` header containing the configured real credentials.
- Keep caller credentials and real Travelport credentials out of SOAP bodies, responses, and logs.
- Keep Travelport's stateless and sessioned SOAP structures intact during authentication.
- Return Travelport session keys as reversible `ENC_` values and restore all repeated occurrences on
  the next request, even when `pii.enabled=false`.
- Reject incomplete or obsolete Travelport credential configuration at startup.
- Specify a red-green-refactor implementation sequence with focused unit and integration tests.

**Non-Goals:**

- Managing, pooling, refreshing, serializing, ending, or retrying Travelport sessions.
- Selecting Travelport endpoints or services; `host`/`proxy_pass` remain deployment configuration.
- Adding a Travelport PII-rule baseline.
- Supporting Travelport JSON APIs or OAuth; this change is only for Universal API SOAP/XML.
- Changing Amadeus or Sabre WS-Security behavior.

## Decisions

### 1. Give Travelport a dedicated header-auth handler

`TravelportHandler` will no longer inherit `SoapSecurityHandler`. It will parse operations with the
existing `_soap_operation`, use a no-op body swap, and set `Authorization` in
`swap_request_headers`.

The handler will construct:

`Basic <base64("Universal API/" + username + ":" + password)>`

with the standard library only. `_set_header` will remove every case variant of a caller-supplied
`Authorization` header before setting the canonical outbound value. The configured `username` is
the assigned username without the `Universal API/` prefix; the relay adds the prefix exactly once.

Alternatives rejected:

- SOAP `UsernameToken`: contradicted by Travelport's Universal API documentation.
- A pre-encoded `authorization` secret: makes prefix/encoding errors opaque and complicates safe
  validation and rotation.
- Reusing `NdcHeaderHandler`: Travelport needs two credential fields, custom formatting, SOAP
  operation parsing, session response cleanup, and credential validation.

### 2. Validate the Travelport credential pair at configuration load

When `credentials.enabled=true`, validation will require non-empty `username` and `password`.
`username` must not contain `:` and neither value may contain control characters; the legacy
Travelport keys `soap_security`, `soap_username`, and `soap_password` will be rejected. Validation
errors name the channel and invalid key/condition but never include values.

Request-time construction will still use `_require_credential` and map unexpected failures to
`credential_swap_failed`, preserving defense in depth if a `ChannelConfig` is constructed outside
the normal loader.

Alternative rejected: accepting both old and new credential forms. The old form cannot authenticate
according to the cited Travelport contract, and silently accepting ignored SOAP secrets would create
a false sense of successful migration.

### 3. Authentication never performs a Travelport request-body swap

`requires_body_inspection` for credential injection will be false and `swap_request_body` will be a
no-op. The handler will not create, replace, or remove SOAP `Security`, `SessionContext`, `SessTok`,
or `SessionKey` data.

The forwarder may still parse a request when PII, operation authorization, or session-token
de-anonymization requires it. Tests will therefore assert semantic preservation of session fields,
not byte-for-byte preservation after XML serialization.

### 4. Treat Travelport SessionKey as response authentication state

For an enabled Travelport credential swap, `requires_response_keyring` will return true. During
response cleanup, the handler will encrypt:

- every attribute whose local name is `SessionKey`; and
- an `id` attribute only when its owning element local name is `SessTok`.

Already valid `ENC_` values remain unchanged. Missing keyring or encryption failure raises
`CredentialSwapError`, producing the existing fail-closed 502 without returning a plaintext session
key. This cleanup runs before PII redaction and does not depend on `pii.enabled`.

On later requests, the existing generic de-anonymization stage restores `ENC_` tokens in all XML
text and attributes before forwarding. This restores both `SessTok/@id` and operation
`@SessionKey`, including duplicate occurrences of the same token. No handler-specific request
replacement is needed.

Alternative rejected: leaving session keys plaintext because they are not the static Basic password.
They authorize access to a live supplier workspace and the repository's credential-cleanup model
already protects replayable Amadeus/Sabre session state.

### 5. Test at handler and complete-forwarder boundaries

Unit tests will pin exact Basic encoding, case-insensitive replacement, disabled behavior, operation
parsing, validation, no-op body swapping, response token encryption/idempotence, and missing-keyring
failure. Integration tests will use `httpx.MockTransport` to prove the upstream receives real Basic
auth but no caller auth, stateless/session XML remains structurally valid, a returned session key is
opaque to the caller, and both replay locations are restored upstream with `pii.enabled=false`.

Sanitized fixtures will model `PingReq`, `BookingStartRsp`, and a sessioned follow-up request using
version-agnostic production-shaped namespaces. No real username, password, branch, passenger data, or
session token will be committed.

## Risks / Trade-offs

- **[Breaking Travelport configuration]** Existing deployments using `soap_security` will fail
  startup. → Ship a migration note and update configuration examples before deployment; fail-fast is
  safer than forwarding an unauthenticated or caller-authenticated request.
- **[Travelport schema versions vary]** Namespace URIs change across releases. → Match documented
  credential/session targets by local element and attribute names while continuing to parse with the
  hardened XML factory.
- **[Session support requires the relay keyring]** Credentialed Travelport startup may now require a
  configured PII keyring even when PII rules are disabled. → Document this requirement and test the
  same startup gate already used for Amadeus/Sabre response-auth encryption.
- **[Basic credentials contain unsupported characters]** Ambiguous delimiters/control characters can
  produce malformed headers. → Reject colon in username and control characters in either field;
  assigned Travelport credentials are expected to be ASCII-compatible.
- **[Generic de-anonymization parses sessioned requests]** XML may be reserialized even though auth is
  header-only. → Assert semantic preservation and gzip round-trip behavior; retain hardened parser
  limits and fail-closed errors.
- **[Over-broad session encryption]** Encrypting every `id` attribute would corrupt unrelated IDs. →
  Scope `id` specifically to `SessTok`; scope `SessionKey` by attribute name.

## Migration Plan

1. Before rollout, configure the relay keyring using the existing secret mechanism.
2. Replace each enabled Travelport `soap_security`/`soap_username` credential set with bare
   `username` and `password` values.
3. Deploy the change; startup validation blocks incomplete migrations before traffic is accepted.
4. Verify with a sanitized/mock Ping flow, then a Booking Start and one sessioned follow-up in the
   target environment without logging headers or bodies.
5. Roll back code and restore the prior config only as an emergency service rollback; the prior
   Travelport auth behavior is not contract-correct. Session tokens already issued as `ENC_` remain
   decryptable while the same keyring is retained.

## Open Questions

- None required for implementation. If production Travelport samples differ from the documented
  `BookingStartRsp/@SessionKey`, `SessionContext/SessTok/@id`, and request `@SessionKey` shapes, add
  sanitized fixtures and a follow-up spec delta before broadening the matcher.
