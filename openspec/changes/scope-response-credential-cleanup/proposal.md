# Scope response credential cleanup to the security/session subtree

## Why

`SoapSecurityHandler.swap_response` (Amadeus/Sabre), `TravelportHandler.swap_response`, and
`TravelfusionHandler.swap_response` all scan the **entire** response tree (`root.iter("*")`) for
elements/attributes matching a bare local name — `SessionId`, `SecurityToken`,
`BinarySecurityToken`, `SessionKey`, `SessTok/@id`, `LoginId`, `XmlLoginId` — anywhere in the
document. Any legitimate business field elsewhere in the payload that happens to share one of these
local names would be silently encrypted (Sabre/Amadeus/Travelport) or stripped (Travelfusion), even
though it is not a credential.

Low likelihood against today's known schemas, but a supplier schema change or an unusual response
shape could corrupt unrelated client-facing data with no error surfaced — and the current
spec/tests don't constrain the match to the auth-bearing region. The Travelport `SessTok/@id` case is
already scoped by owner-element name; the other matches are not.

## What Changes

- Response credential cleanup SHALL match authentication fields only within the response's WS-Security
  header / documented session block (e.g. under `Security`, an `awsse:Session`, or the channel's known
  session envelope path), not by a document-wide local-name scan. A same-named element/attribute
  outside that region SHALL be left untouched.

## Capabilities

### Modified Capabilities
- `channel-credential-swap`: response credential cleanup is scoped to the security/session subtree;
  same-named business fields elsewhere are not encrypted or stripped.

## Impact

- `src/channel_relay/channels/handlers.py`: scope the `swap_response` scans (SOAP/Travelport/
  Travelfusion) to the security/session region instead of `root.iter("*")`.
- `tests/unit/test_channel_credential_swap.py`: add cases asserting a same-named field outside the
  security/session subtree is left unchanged; confirm the real auth fields are still handled.
