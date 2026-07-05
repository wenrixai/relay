---
name: channel-implementation
description: Wenrix channel-relay playbook for adding a new supplier channel (route, config, credential-swap handler, registry) and for authoring or editing PII anonymization baseline rules from real payloads. ALWAYS invoke when adding/onboarding a channel or GDS (e.g. "add Kiwi", "onboard Travelport ops"), writing/editing rules in rules_fallback.json, sanitizing supplier payload fixtures, or writing channel golden tests. NOT for deploying/operating the relay, generic pytest questions, or OpenSpec mechanics (use the openspec-* skills for the change loop itself).
---

# Channel Implementation & PII Rule Authoring

## Purpose

Adding a channel to the Wenrix relay means: a `ChannelType` + config defaults, a credential-swap
handler wired into the registry, baseline PII rules distilled from real payloads, sanitized
fixtures, and golden tests. This skill encodes the proven end-to-end procedure so each new
channel lands with few errors and no real PII in git. Success = `just ci` green, zero plaintext
PII surviving redaction, encrypted fields round-tripping, and the raw payloads never committed.

## Hard constraints (from repo instructions — violations are security bugs)

- Never commit, log, or leave in the working tree unsanitized supplier payloads; they contain
  real passenger data and live session credentials.
- XML only via the hardened parser factory (`src/channel_relay/pii/xml_ops.py`); credential
  swaps and redaction are structural — never regex find-and-replace on bodies.
- Operation names come from the request/response body, never from headers.
- No retries, no slow tests, no real network in the suite.
- Non-trivial work goes through the OpenSpec loop first (propose → apply → archive).

## Workflow

### A. Adding a new channel

1. Collect 3+ real payloads per operation (requests AND responses) from the supplier.
2. Analyze payloads: operation identification, namespaces, credential/auth locations,
   PII fields (element text AND attributes). Fan out subagents for large payload sets.
3. Implement the handler + registry entry → read `references/channel-handler.md`.
4. Author baseline PII rules → read `references/pii-rules.md`.
5. Sanitize fixtures + write golden/integration tests → read `references/fixtures-and-tests.md`.
6. Close out: `just ci`, delete/gitignore raw payloads, conventional commit, archive the
   OpenSpec change.

### B. Editing PII rules for an existing channel

1. Reproduce the gap: run the relevant golden test or redact the fixture in a scratch script.
2. Verify the real XML shape in `tests/fixtures/<channel>/` before writing any XPath — payload
   element names vary between near-identical variants (see pitfalls in `references/pii-rules.md`).
3. Write the failing test first, then edit `src/channel_relay/pii/rules_fallback.json`; bump
   `rules_version`.
4. Run the channel's unit + integration suites, then `just ci`.

## References

- `references/channel-handler.md` — ChannelType, config models, handler protocol/mixins,
  registry, forwarder pipeline order, error contract. Read when touching anything under
  `src/channel_relay/channels/` or `src/channel_relay/config/`.
- `references/pii-rules.md` — rule schema capabilities, XPath + namespace conventions, action
  policy (encrypt vs mask), DRY levers, and the pitfall list learned from Amadeus + Sabre.
  Read before writing or editing any rule.
- `references/fixtures-and-tests.md` — payload sanitization protocol, golden unit-test and
  relay integration-test patterns, shared conftest fixtures, CI gates. Read before creating
  fixtures or tests.

## Existing examples to mirror

- Handler spectrum: `src/channel_relay/channels/handlers.py` (header-only NDC, XML-element
  Travelfusion, XML-attribute Farelogix, SOAP-security Amadeus/Sabre/Travelport).
- Rules: `src/channel_relay/pii/rules_fallback.json` (`amadeus.*` and `sabre.*` baselines).
- Tests: `tests/unit/test_pii_sabre.py`, `tests/integration/test_pii_sabre_relay.py`.
