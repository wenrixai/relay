## Why

Travelport Universal API SOAP requests authenticate with HTTP Basic authorization, using
`Universal API/<username>:<password>`, not a WS-Security `UsernameToken`. The relay currently treats
Travelport like Amadeus/Sabre and replaces a SOAP `Security` element, which can forward the wrong
HTTP credentials and can overwrite Travelport session context.

## What Changes

- Replace Travelport's SOAP-security body swap with case-insensitive outbound `Authorization` header
  replacement using configured `username` and `password`.
- Generate the standard Basic value from `Universal API/<username>:<password>` inside the relay;
  callers never provide the real encoded value.
- Require both Travelport credential fields at configuration load when credential swap is enabled,
  and fail closed without forwarding if header construction cannot complete.
- Preserve Travelport SOAP bodies during authentication, including `SessionContext/SessTok/@id` and
  operation-level `SessionKey` attributes used by sessioned booking requests.
- Encrypt Travelport `BookingStartRsp/@SessionKey` before returning it to the caller and decrypt every
  replayed occurrence before forwarding a later sessioned request, independent of `pii.enabled`.
- Add sanitized stateless and sessioned fixtures plus red-green-refactor unit and mocked-forwarder
  integration coverage; no test calls Travelport.
- **BREAKING**: Travelport credential configuration changes from the incorrect `soap_security` /
  `soap_username` form to required `username` and `password` fields.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `channel-credential-swap`: define Travelport Universal API HTTP Basic credential replacement,
  fail-fast configuration validation, body-preserving session behavior, and reversible protection of
  Travelport session keys.

## Impact

- Code: Travelport gets a dedicated handler in `src/channel_relay/channels/handlers.py`; the existing
  registry entry remains, while shared Amadeus/Sabre SOAP-security behavior is unchanged.
- Configuration: Travelport deployments must migrate enabled credentials to `username` and
  `password`; generated JSON Schema remains pydantic-derived.
- Tests/fixtures: replace the inaccurate Travelport WS-Security fixture and add session start/replay
  fixtures, handler unit tests, config validation tests, and mocked `httpx` forwarder tests.
- Security: client-supplied `Authorization` values are overwritten case-insensitively, real
  credentials never enter bodies or responses, session keys are opaque to callers, errors contain no
  credential material, and all XML handling continues through the hardened parser.
- Dependencies/network: no new dependency, retry, polling, or live supplier call.
