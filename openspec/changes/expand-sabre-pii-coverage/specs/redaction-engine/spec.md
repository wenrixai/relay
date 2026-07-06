# redaction-engine Specification

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
(`encrypt` → `ENC_` token, `mask`, `replace`, `remove`).

Phase 2 (`reference` rules): for each selected `reference` rule, locate its target nodes by XPath
and replace occurrences of the values collected under its `source_pii_types` per the referential
matching rules, using its `encrypt` action.

The relay SHALL then re-serialize once, preserving structure, namespaces, and declarations. Channels
without PII enabled SHALL pass through untouched. Rules with `path_type: jsonpath` are loaded but
skipped in this slice. A channel with only `field` rules behaves exactly as before (phase 2 is a
no-op).

The redaction pass SHALL report a coverage outcome alongside the redacted body: the parsed operation
name and whether **any** rule (`field` or `reference`) matched the channel+operation. This lets the
forwarder emit the coverage-gap metric, distinguishing "matched rules, redacted nothing" from "no
rules matched this operation" — the two are otherwise indistinguishable from the per-field counts
alone. An uncovered operation SHALL still be forwarded unchanged; the coverage outcome is
observability only and never blocks or errors.

#### Scenario: Coverage outcome reports zero matches
- **WHEN** a response operation matches no `field` or `reference` rules for the channel
- **THEN** the redaction pass returns the (unchanged) body and a coverage outcome flagging the
  operation as unmatched, and the body is forwarded to the client

#### Scenario: Coverage outcome reports a match
- **WHEN** at least one rule matches the operation (even if it rewrites zero values)
- **THEN** the coverage outcome flags the operation as covered

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
