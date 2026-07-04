## Why

Structured field rules only redact PII that sits in its own node (e.g. `//Passenger/First`).
Airline back-office channels also carry the *same* PII embedded in free-text notes — Amadeus/Sabre
remark fields ("RM PSGR JOHN SMITH RQ WHEELCHAIR"), OSI/SSR text, comments. Today those names leak
to the channel un-redacted. We need a rule that anonymizes free text by reusing the PII values that
structured rules already extracted from the same document — "de-anonymize the name wherever it also
appears in prose."

## What Changes

- Add a new rule kind `rule_type: reference` to the PII ruleset (discriminated alongside the
  existing `field`). A reference rule declares `source_pii_types` (which extracted values to hunt),
  a target `path`/`path_type`/`namespaces` (which free-text nodes to search — bounded, never
  document-wide), match guards (`min_match_len`, `word_boundary`, case-insensitivity), and a
  reversible `encrypt` action.
- Response redaction becomes **two-phase within one pass**: phase 1 collects the plaintext values
  matched by field rules (grouped by `pii_type`) *before* it rewrites those nodes; phase 2 searches
  the reference rule's target nodes for those collected values and replaces each occurrence in place.
- **BREAKING (behavioral, internal):** request de-anonymization changes from full-match to an
  embedded-token scan so `ENC_` tokens sitting *inside* free text round-trip back to plaintext for
  the channel. Full-match tokens keep working unchanged.
- Reference matching is literal (a collected value is a fixed string, never a regex) and structural
  (operates on the parsed node's text, never a regex find-and-replace on the raw body).

## Capabilities

### New Capabilities
- `referential-redaction`: collecting extracted PII values within a document and redacting their
  occurrences inside bounded free-text nodes, including match-guard semantics and fail-closed rules.

### Modified Capabilities
- `pii-rules`: the rule schema gains the `reference` rule kind (new discriminated model, its
  parameters, and load-time validation) alongside `field`.
- `redaction-engine`: response redaction gains the collect→search two-phase ordering; request
  de-anonymization changes from full-match to embedded `ENC_` token scan.

## Impact

- Code: `src/channel_relay/pii/rules.py` (new `ReferenceRule` model + union), `engine.py`
  (two-phase redaction, embedded de-anon), generated rules JSON Schema, baked fallback bundle.
- Metrics: `pii_fields_redacted_total` gains reference-rule attribution; no new secret material.
- Docs: relay-configuration spec rule reference, PII rule-authoring checklist. No `WP_*` config change.
- Security: still confidentiality-only; no new persistence (values live only for the one pass — no
  cross-request memory). Over-redaction risk in free text is contained by guards + bounded paths.
