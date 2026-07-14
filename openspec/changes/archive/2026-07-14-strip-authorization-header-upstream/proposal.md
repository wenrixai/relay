# Strip the client Authorization header before forwarding upstream

## Why

The relay authenticates clients with a single shared HTTP basic-auth credential
(`basic_auth_user`/`basic_auth_pass`). That credential arrives as an `Authorization: Basic …` request
header. `clean_request_headers` (`middleware/header_hygiene.py`) strips hop-by-hop, forwarding,
`x-wenrix-*`, and `Proxy-*` headers and rewrites `Host` — but it does **not** strip `Authorization`.
`middleware/auth.py` only validates the header; it never removes it. `proxy/forwarder.py` then builds
the upstream headers straight from `clean_request_headers(...)` and sends them to the channel.

Only `TravelportHandler` overwrites `Authorization` (with real channel creds). For Amadeus, Sabre, and
Travelfusion the credential swap is body-only (WSSE/structural); Farelogix and the NDC channels set a
*different* header (`Ocp-Apim-Subscription-Key` / an API-key header) and leave `Authorization`
untouched; zero-config pass-through channels forward it verbatim.

**Result.** The relay's shared client-auth secret is forwarded, in the clear at the application layer,
to third-party GDS/NDC endpoints on nearly every request. Anyone with visibility into a channel's
access logs, WAF, or infrastructure can harvest and replay it to impersonate any client of the relay —
a full auth bypass. It also breaks transparency (D11, §9.1): an `Authorization: Basic …` header keyed
to the relay's realm reveals an intermediary the channel must never see.

`openspec/specs/header-hygiene/spec.md` and `docs/PROJECT.md` §9.1 both share this gap — the
requirement itself omits `Authorization` — so this is a genuine spec change, not just a code fix.

## What Changes

- The request-path drop set SHALL include `Authorization`: the relay strips the client's
  `Authorization` header before forwarding, so it never reaches the channel.
- A channel that legitimately needs an outbound `Authorization` (e.g. Travelport Basic auth) SHALL set
  it explicitly during credential swap — which already happens, and now becomes the *only* way an
  `Authorization` header reaches a channel.

## Capabilities

### Modified Capabilities
- `header-hygiene`: `Authorization` is stripped on the request path with the other client-facing
  identity headers; only a credential-swap handler may set an outbound `Authorization`.

## Impact

- `src/channel_relay/middleware/header_hygiene.py`: add `authorization` to `_drop_request`.
- `tests/unit/test_header_hygiene.py`: assert `Authorization` never survives to the channel for a
  non-swap / pass-through channel; assert Travelport's swapped `Authorization` still reaches the
  channel (swap runs after hygiene).
- `docs/PROJECT.md` §9.1: add `Authorization` to the documented strip list.
