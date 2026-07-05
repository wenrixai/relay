# redaction-engine Specification Delta

## Modified Requirements

### Requirement: Response redaction

For channels with `pii.enabled: true`, the relay SHALL redact channel responses before returning
them to the client in a single pass over two phases:

Phase 1 (structured `field` rules): parse the XML via the hardened factory, parse the operation from
the body using the configured channel handler when the relay has channel context, select `field`
rules where `channel` matches the configured channel type value and the `operation` regex matches,
locate nodes by XPath using rule-declared namespaces, skip values matching
`ignored_content_patterns`, collect the located plaintext value into the rule's `pii_type` bucket
BEFORE rewriting, then apply the rule's action (`encrypt` → `ENC_` token, `mask`, `replace`,
`remove`).

Phase 2 (`reference` rules): for each selected `reference` rule, locate its target nodes by XPath
and replace occurrences of the values collected under its `source_pii_types` per the referential
matching rules, using its `encrypt` action.

The relay SHALL then re-serialize once, preserving structure, namespaces, and declarations. Channels
without PII enabled SHALL pass through untouched. Rules with `path_type: jsonpath` are loaded but
skipped in this slice. A channel with only `field` rules behaves exactly as before (phase 2 is a
no-op).

#### Scenario: Travelfusion wrapper operation parsed by handler

- **WHEN** a PII-enabled Travelfusion route named `tf` returns `<CommandList><GetBookingDetails>...`
- **THEN** rule selection uses channel `travelfusion` and operation `GetBookingDetails`

#### Scenario: Travelfusion PII is reversible

- **WHEN** Travelfusion PII rules match passenger, contact, billing, address, or payment fields
- **THEN** every matched value is replaced with an `ENC_` token and decrypts back to the original value

#### Scenario: Golden redaction

- **WHEN** a PII-enabled channel returns a fixture response with rule-matched fields
- **THEN** the client receives the fixture with those fields replaced per each rule's action, and
  decrypting the `ENC_` tokens recovers the original values
