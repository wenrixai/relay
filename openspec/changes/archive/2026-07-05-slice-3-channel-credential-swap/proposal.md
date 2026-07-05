# Proposal: slice-3-channel-credential-swap

## Why

Slice 3 turns the relay from a generic transparent/PII pipeline into a channel-aware relay. Each
configured channel needs a body-derived operation parser and an opt-in structural credential swap so
callers can send placeholder or stale supplier credentials while the relay forwards only configured
channel credentials.

## What Changes

- Add a channel handler abstraction and registry keyed by `ChannelType`.
- Parse operations from request bodies only; never trust operation headers.
- Wire credential swap into the existing forwarding pipeline after request de-anonymization and
  before the upstream call.
- Implement per-channel swaps for Travelfusion, BA NDC, LA NDC, Farelogix AA/LH/UA/EK, Amadeus,
  Sabre, and Travelport.
- Add Sabre/Amadeus response auth-field encryption using the existing token codec and keyring.
- Preserve zero-config pass-through: channels without credentials do not mutate request bodies.

## Impact

- Code: new `src/channel_relay/channels/` handlers plus forwarder/content wiring.
- Config: existing `credentials` map becomes behavior-bearing for channel-specific keys; generated
  schema remains pydantic-first.
- Tests: sanitized golden fixtures under `tests/fixtures/<channel>/` drive parser, request swap,
  response strip/encryption, and forwarder behavior.
- Security: all XML parsing uses the hardened parser; credential-swap failures fail closed with the
  existing `credential_swap_failed` error reason.
