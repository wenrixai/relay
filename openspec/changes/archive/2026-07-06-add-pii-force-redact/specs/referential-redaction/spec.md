## MODIFIED Requirements

### Requirement: Reference redaction of bounded free-text nodes

For channels with `pii.enabled: true`, a `reference` rule SHALL search the text of the nodes located
by its own `path` (using its declared `namespaces`) for occurrences of the values collected under
its `source_pii_types`, and SHALL replace each matched span in place using its action (reversible
`encrypt`, unless the channel has `pii.force_redact: true`, in which case each matched span is
replaced with the fixed literal `"REDACTED"` instead — no crypto codec call, no keyring required).
The search SHALL be confined to those located nodes — never the whole document — and SHALL run in a
second phase, after value collection, within the same pass. The rewrite SHALL be structural: it
edits the parsed node's text, never the raw body, and treats each collected value as a fixed literal
(never a regex). A reference rule whose `source_pii_types` buckets are all empty SHALL match nothing.

#### Scenario: Name scrubbed from remark
- **WHEN** `person` was collected as {"John", "Smith"} and a `reference` rule targets
  `//Remark/Text` = "PSGR JOHN SMITH RQ WHEELCHAIR"
- **THEN** each name occurrence is replaced by an `ENC_` token, the surrounding text ("PSGR ",
  " RQ WHEELCHAIR") is preserved, and decrypting each token recovers "John" / "Smith"

#### Scenario: Search bounded to target path
- **WHEN** a collected value also appears in a node NOT located by the reference rule's `path`
- **THEN** that other node is left unmodified

#### Scenario: Unknown namespace prefix is a no-match
- **WHEN** a reference rule's `path` uses a namespace prefix absent from its declarations
- **THEN** it matches nothing, a warning metric is emitted, and processing continues

#### Scenario: force_redact substitutes a fixed placeholder in free text
- **WHEN** a channel has `pii.force_redact: true` and a reference rule matches "John" inside
  `//Remark/Text` = "PSGR JOHN SMITH RQ WHEELCHAIR"
- **THEN** each matched name is replaced with the literal `"REDACTED"`, the surrounding text is
  preserved, and no `ENC_` token is produced

## ADDED Requirements

### Requirement: force_redact needs no keyring for reference redaction

When a channel has `pii.force_redact: true`, reference-rule redaction SHALL NOT require a
configured keyring — the substitution is the fixed literal `"REDACTED"`, never a call to the crypto
codec.

#### Scenario: Reference redaction succeeds without a keyring
- **WHEN** a `pii.force_redact: true` channel's reference rule matches free text and no
  `RELAY_PII_KEYRING` is configured
- **THEN** the matched spans are replaced with `"REDACTED"` and no error is raised
