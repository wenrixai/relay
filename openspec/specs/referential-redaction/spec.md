# referential-redaction Specification

## Purpose
Redact PII that appears inside bounded free-text nodes by referencing the plaintext values collected
from structured `field` rules during the same response-redaction pass, so that names and other
identifiers embedded in remarks and prose are scrubbed reversibly without scanning the whole document.
## Requirements
### Requirement: Within-document value collection

During response redaction the relay SHALL collect the plaintext values matched by `field` rules,
grouped by `pii_type`, captured BEFORE those nodes are rewritten. The collection SHALL live only for
the duration of the single redaction pass on that one document; it SHALL NOT be persisted, logged,
or shared across requests or documents. When no `field` rule matches a value, the corresponding
bucket is empty.

#### Scenario: Plaintext captured before rewrite
- **WHEN** a `field` rule with `pii_type: person` and `method: encrypt` matches `//Passenger/First`
  holding "John"
- **THEN** the collected `person` bucket contains "John" (the plaintext), even though the node's
  text is rewritten to an `ENC_` token in the same pass

#### Scenario: No cross-request memory
- **WHEN** a value is collected during one request's redaction
- **THEN** it is discarded when that pass ends and is not available to any later request

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

### Requirement: Match guards against over-redaction

Reference matching SHALL apply guards: values shorter than `min_match_len` (default 3) SHALL be
skipped; when `word_boundary` is true (default), a value SHALL match only when bordered by a
non-alphanumeric character or a string edge; comparison SHALL be case-insensitive while the original
casing of surrounding, unmatched text is preserved.

#### Scenario: Short value skipped
- **WHEN** a collected value "Li" is shorter than `min_match_len` 3
- **THEN** it is not searched and free text containing "Li" is left unmodified

#### Scenario: Word boundary prevents substring hit
- **WHEN** `word_boundary` is true, "John" is collected, and free text contains "Johnson"
- **THEN** "Johnson" is not redacted

#### Scenario: Case-insensitive match preserves surrounding casing
- **WHEN** "John" is collected and free text contains "john smith"
- **THEN** "john" is replaced by a token and " smith" is left as-is

### Requirement: Fail-closed reference redaction

Any crypto, rule, or XML error during reference collection or redaction SHALL produce the 502
`pii_redaction_failed` error contract and the relay SHALL NOT forward a partially processed body.
Error details SHALL never contain PII, tokens, or key material. Reference-rule actions SHALL count
toward `pii_fields_redacted_total` attributed to the rule's `pii_type`.

#### Scenario: Encrypt failure drops response
- **WHEN** encrypting a matched free-text span fails mid-document
- **THEN** the client receives 502 `pii_redaction_failed` and none of the upstream body

#### Scenario: Reference redaction counted
- **WHEN** a reference rule replaces two name occurrences in a remark
- **THEN** `pii_fields_redacted_total` for that `pii_type` increases by two

### Requirement: Reference hits reuse collected-value tokens
A reference-rule hit SHALL reuse the token already minted during the same pass for the identical
exact plaintext under the same encryption mode (the phase-1 field-rule token, or an earlier
reference hit's token), instead of re-encrypting with a fresh IV. When no token exists yet for that
exact plaintext and mode, the reference rule SHALL encrypt per its own action and the result SHALL
join the pass-scoped cache. Because reference matching is case-insensitive while encryption
preserves the matched casing, a case-variant occurrence SHALL be encrypted as its own exact
plaintext (round-trip casing fidelity outranks cross-casing token equality).

#### Scenario: Remark occurrence shares the field token
- **WHEN** a field rule encrypts `//Passenger/Last` holding "SMITH" and a reference rule then hits
  "SMITH" inside a remark in the same response
- **THEN** the remark span is replaced with the same `ENC_` token the field received

#### Scenario: Repeated remark hits share one token
- **WHEN** the same collected value occurs twice inside reference-rule target text
- **THEN** both spans receive the identical token and the redaction count increases by two

#### Scenario: Case variant gets its own token
- **WHEN** "Smith" was collected and tokenized, and a remark contains "SMITH"
- **THEN** "SMITH" is matched (case-insensitive) but encrypted as "SMITH", yielding a token that
  decrypts to "SMITH", distinct from the "Smith" token

### Requirement: force_redact needs no keyring for reference redaction

When a channel has `pii.force_redact: true`, reference-rule redaction SHALL NOT require a
configured keyring — the substitution is the fixed literal `"REDACTED"`, never a call to the crypto
codec.

#### Scenario: Reference redaction succeeds without a keyring
- **WHEN** a `pii.force_redact: true` channel's reference rule matches free text and no
  `RELAY_PII_KEYRING` is configured
- **THEN** the matched spans are replaced with `"REDACTED"` and no error is raised
