# Require resolvable upstream and complete swap credentials at startup

## Why

Two fail-closed startup gaps let a misconfigured channel boot "ready" and then fail every request,
discoverable only once traffic arrives — the opposite of the abort-on-misconfig golden rule.

1. **Channel with no resolvable upstream boots ready.** `_DEFAULT_HOSTS[LA_NDC_DIRECT]` and
   `[TRAVELPORT]` are `None` (`config/models.py`). A channel of one of these types configured without
   `host`/`proxy_pass` passes pydantic validation (both fields are `str | None`, no cross-field check),
   and `readiness_reasons` (`health.py`) only checks `config is None` — so `/readiness` reports ready.
   Every real request then hits `forward()`, which returns `internal_error` because
   `channel.proxy_pass is None`. Broken for every request, silently, until traffic hits it.

2. **Three of six swap handlers never validate credentials at load.** `main.validate_credential_config`
   iterates channels and calls `handler.validate_credentials(channel)`, and its docstring says it
   "aborts startup when a swap-enabled channel lacks the credentials its handler requires." But
   `TravelfusionHandler`, `NdcHeaderHandler`, and `FarelogixHandler` inherit
   `NoCredentialValidationMixin`, whose `validate_credentials` is an unconditional no-op — only the SOAP
   (Amadeus/Sabre) and Travelport handlers actually check. A Farelogix channel with
   `credentials.enabled: true` and a missing `password`, or an NDC channel missing its API key, boots
   successfully and then fails **every** request with `credential_swap_failed`/502.

## What Changes

- Startup SHALL abort when any configured channel has no resolvable upstream (`proxy_pass` still
  `None` after per-type host defaulting), naming the channel — rather than booting ready and 500-ing
  per request. (Alternatively surfaced as a readiness reason, but abort matches the existing
  fail-closed posture for invalid config.)
- Every credential-swap-enabled handler SHALL validate its required credential fields at configuration
  load and abort startup on a missing/invalid field, naming the channel and condition without leaking
  any credential value. Extend real `validate_credentials` to Travelfusion, Farelogix, and the NDC
  header handlers (mirroring the SOAP/Travelport pattern).

## Capabilities

### Modified Capabilities
- `relay-configuration`: startup aborts when a channel resolves to no upstream base.

### Modified Capabilities
- `channel-credential-swap`: credential-configuration validation at load applies to **all**
  swap-enabled channel types, not only Travelport/SOAP.

## Impact

- `src/channel_relay/config/models.py` or `src/channel_relay/main.py`: validator that aborts when a
  channel's `proxy_pass` is unresolved after defaulting.
- `src/channel_relay/channels/handlers.py`: implement `validate_credentials` for Travelfusion,
  Farelogix, and NDC handlers (drop `NoCredentialValidationMixin` where it hides a real requirement).
- `tests/unit/test_main_startup.py`, `tests/unit/test_config.py`,
  `tests/unit/test_channel_credential_swap.py`: startup-abort tests for both gaps.
