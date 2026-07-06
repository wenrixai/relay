## Context

`ChannelPII` today has one field, `enabled`. The action a matched field gets is fixed
per rule in the shared rules JSON (`encrypt`/`mask`/`replace`/`remove`), never
customer-configurable. Reference rules are hardcoded to `encrypt` in v1 and call the
codec directly, bypassing the field-rule action dispatch (`_apply_action`) entirely.
Some customers do not want reversible encryption at all; forking rules per customer to
give them `mask`/`replace` instead of `encrypt` would fragment the ruleset and require
per-customer rule maintenance instead of a single config toggle.

## Goals / Non-Goals

**Goals:**
- One per-channel boolean (`pii.force_redact`) that, when true, makes every `encrypt`
  outcome for that channel resolve to a fixed, non-reversible placeholder.
- No new keyring requirement for a channel that only uses `force_redact`.
- No behavior change for channels that don't set it (default `false`).

**Non-Goals:**
- No new `RedactAction` rule type in the rules schema — this is an apply-time
  override, not a new discriminated action. Rules keep saying `method: encrypt`; the
  channel config decides whether that's honored or overridden.
- No change to `mask`/`replace`/`remove` actions — only `encrypt` is affected.
- No per-rule or per-customer granularity — this is a per-channel switch.

## Decisions

**Fixed placeholder is the literal `"REDACTED"`**, not a length-preserving mask or
field removal (user decision). Simplest, unambiguous, and matches the existing
`ReplaceAction` semantics without needing a `replacement` parameter.

**Apply-time override, not a rules-schema change.** Adding a `force_redact` flag as a
parameter threaded through `_apply_action` / `_redact_reference_rule` /
`redact_response_body` keeps the ruleset itself customer-agnostic — the same rules JSON
serves every customer of a channel type, and the config layer decides the encrypt
outcome. Alternative considered: a `RedactAction` rule variant or per-customer rule
forks — rejected because it multiplies rules per customer and drifts from the "rules
are channel-type-scoped, not customer-scoped" model already in place.

**Reference rules are covered too.** `ReferenceRule.action` is typed `EncryptAction`
only, and `_redact_reference_rule` calls `encrypt()` unconditionally. Since the user
wants "no encryption ever" for a force_redact channel, this path also needs the
override — otherwise free-text reference redaction would still leak `ENC_` tokens for a
customer who explicitly opted out of encryption.

**Keyring becomes optional on the redact-heavy paths.** `_apply_action`,
`_redact_reference_rule`, and `redact_response_body` accept `keyring: Keyring | None`
since the force_redact branch never touches the codec. `build_keyring`'s
`keyring_required` predicate is narrowed to `(pii.enabled and not force_redact) or
credentials_require_response_keyring(channel)` so a deployment with only
force_redact channels doesn't need `RELAY_PII_KEYRING` configured at all. This also
requires updating `crypto-keyring`'s existing requirement ("PII enabled without keyring
aborts startup") to carve out the force_redact case.

**Request-side de-anonymization is untouched.** A force_redact channel never produces
`ENC_` tokens, so there's nothing to decrypt on the way back in; the existing
`keyring is not None` gate on `deanonymize_request_body` already no-ops correctly when
no keyring is configured for such a channel.

## Risks / Trade-offs

- **Silent behavior change if a channel is later toggled.** Turning `force_redact` on
  for a channel that has previously issued `ENC_` tokens to a client doesn't retroactively
  fix already-issued tokens — mitigated by this being an explicit, documented opt-in
  config change, not a runtime toggle; treated the same as any other channel config
  edit that requires a restart.
- **Two independent booleans (`enabled`, `force_redact`) instead of one enum.** Slightly
  more state space (`force_redact: true, enabled: false` is a no-op) but matches the
  existing `pii.enabled` pattern and keeps the diff minimal; validation doesn't need to
  reject the redundant combination since it's simply inert.

## Migration Plan

No data migration. Deploying is additive: default `force_redact: false` preserves
current behavior for every existing channel config. Customers who want it set
`pii.force_redact: true` on their channel entry and (if no other channel on the
deployment needs real encryption) can drop `RELAY_PII_KEYRING` entirely.

## Open Questions

None outstanding — placeholder value and reference-rule coverage were resolved with
the user before writing this design.
