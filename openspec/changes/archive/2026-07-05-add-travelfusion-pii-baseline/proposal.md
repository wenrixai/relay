# Add Travelfusion PII Baseline

## Why

Travelfusion already has channel configuration and credential-swap support, but PII redaction does
not cover Travelfusion booking responses. Its XML responses are wrapped in `CommandList`, so generic
non-SOAP operation parsing selects the wrapper instead of operations such as `GetBookingDetails`.
Rule selection also uses the configured route name, which prevents a route like `tf` from matching
rules authored for the Travelfusion channel type.

## What Changes

- Select PII rules by `channel.type.value` while preserving route names for `/channel/<name>/...`.
- Let response redaction use the selected channel handler's body-derived operation parser.
- Add a Travelfusion baked-rule baseline for booking-profile passenger, contact, billing, address,
  and payment fields; all Travelfusion PII fields are encrypted, not masked or removed.
- Add sanitized Travelfusion golden fixtures and relay integration coverage.

## Non-goals

- Do not add new rule schema fields or raw-body regex replacement.
- Do not commit raw external supplier payloads.
- Do not change existing Travelfusion credential-swap semantics.
