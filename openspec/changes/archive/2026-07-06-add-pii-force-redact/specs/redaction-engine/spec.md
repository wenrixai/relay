## MODIFIED Requirements

### Requirement: Response redaction

For channels with `pii.enabled: true`, the relay SHALL redact channel responses before returning
them to the client in a single pass over two phases:

Phase 1 (structured `field` rules): parse the XML via the hardened factory, parse the operation from
the body using the configured channel handler when the relay has channel context, select `field`
rules where `channel` matches the configured channel type value (falling back to the route name when
no type-scoped rule matches that operation) and the `operation` regex matches, locate nodes by XPath
using rule-declared namespaces, skip values matching `ignored_content_patterns`, collect the located
plaintext value into the rule's `pii_type` bucket BEFORE rewriting, then apply the rule's action
(`encrypt` → `ENC_` token, `mask`, `replace`, `remove`). When the channel has `pii.force_redact: true`,
an `encrypt` action SHALL instead replace the value with the fixed literal `"REDACTED"`; no crypto
codec call and no keyring are required for that field.

Phase 2 (`reference` rules): for each selected `reference` rule, locate its target nodes by XPath
and replace occurrences of the values collected under its `source_pii_types` per the referential
matching rules, using its `encrypt` action (or, for a `pii.force_redact: true` channel, the same
`"REDACTED"` substitution as phase 1).

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

#### Scenario: Free-text reference redaction after collection

- **WHEN** a `field` rule collects `person` values and a `reference` rule targets a remark node
  containing those names
- **THEN** the names inside the remark are replaced by `ENC_` tokens in the same pass, and the
  structured fields are also redacted

#### Scenario: Ignored pattern skipped

- **WHEN** a located node's text matches an `ignored_content_patterns` entry
- **THEN** that value is left unmodified

#### Scenario: Unknown namespace prefix is a no-match

- **WHEN** a rule path uses a namespace prefix absent from its declarations
- **THEN** the rule matches nothing, a warning metric is emitted, and processing continues

#### Scenario: PII disabled passes through

- **WHEN** a channel without `pii.enabled` returns a response containing PII
- **THEN** the body is relayed byte-identical

#### Scenario: force_redact substitutes a fixed placeholder

- **WHEN** a channel has `pii.enabled: true` and `pii.force_redact: true`, and a matched field's
  rule action is `encrypt`
- **THEN** the field's value in the response is the literal `"REDACTED"`, not an `ENC_` token, and
  no keyring is consulted for that field

#### Scenario: force_redact channel needs no keyring

- **WHEN** a deployment has no other channel requiring real encryption, and the only PII-enabled
  channel has `pii.force_redact: true`
- **THEN** response redaction for that channel succeeds with no `RELAY_PII_KEYRING` configured
