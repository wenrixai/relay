## MODIFIED Requirements

### Requirement: Response redaction

For channels with `pii.enabled: true`, the relay SHALL redact channel responses before returning
them to the client in a single pass over two phases:

Phase 1 (structured `field` rules): parse the XML via the hardened factory, parse the operation from
the body, select `field` rules where `channel` matches and the `operation` regex matches, locate
nodes by XPath using rule-declared namespaces, skip values matching `ignored_content_patterns`,
collect the located plaintext value into the rule's `pii_type` bucket BEFORE rewriting, then apply
the rule's action (`encrypt` → `ENC_` token, `mask`, `replace`, `remove`).

Phase 2 (`reference` rules): for each selected `reference` rule, locate its target nodes by XPath
and replace occurrences of the values collected under its `source_pii_types` per the referential
matching rules, using its `encrypt` action.

The relay SHALL then re-serialize once, preserving structure, namespaces, and declarations. Channels
without PII enabled SHALL pass through untouched. Rules with `path_type: jsonpath` are loaded but
skipped in this slice. A channel with only `field` rules behaves exactly as before (phase 2 is a
no-op).

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

### Requirement: Request de-anonymization

For channels with `pii.enabled: true`, the relay SHALL de-anonymize requests envelope-driven (no
rules required): parse the XML, scan text and attribute values for `ENC_` tokens — matching each
occurrence of the token contract (`TOKEN_RE`) whether it constitutes the entire value or is embedded
within surrounding free text — decode and decrypt each via the keyring (epoch from the control byte,
smaz-decompress when flagged), splice the plaintext over each matched span, re-serialize, and
forward. The channel always receives plaintext.

Failure semantics differ by shape, because an embedded `ENC_`-prefixed word in prose is ambiguous
(a user may legitimately type it) whereas a whole-value token is not: when a value is EXACTLY one
token (`fullmatch`) and it fails to decode/decrypt, the relay SHALL fail closed (502
`pii_deanonymization_failed`, nothing forwarded); when a token is EMBEDDED among other text and that
span fails to decode/decrypt, the relay SHALL leave that span untouched and continue (no PII leak —
the ciphertext-looking text forwards as-is under confidentiality-only + TLS integrity).

#### Scenario: Round-trip
- **WHEN** a value redacted from an earlier response is sent back as an `ENC_` token in a request
- **THEN** the channel receives the original plaintext value

#### Scenario: Embedded token round-trip
- **WHEN** a request field contains an `ENC_` token embedded in free text (e.g. "PSGR ENC_… RQ")
- **THEN** the token is decrypted in place and the channel receives the surrounding text with the
  plaintext name spliced back in

#### Scenario: Token adjacent to punctuation de-anonymizes
- **WHEN** an embedded token is immediately followed by punctuation (e.g. "…ENC_…, ")
- **THEN** the token boundary ends at the punctuation and it decrypts correctly

#### Scenario: Non-token values untouched
- **WHEN** a request contains values that do not contain any `ENC_` token
- **THEN** they are forwarded unmodified

#### Scenario: Embedded lookalike that fails to decrypt is left untouched
- **WHEN** a value contains an embedded `ENC_`-prefixed span that is not a decryptable token
  (e.g. free text "Plain Name ENC_not a token")
- **THEN** that span is left as-is, the request is forwarded (200), and no 502 is raised

#### Scenario: Full-value bad token fails closed
- **WHEN** a value is EXACTLY one `ENC_` token that fails decoding or decryption
- **THEN** the channel receives nothing and the client gets 502 `pii_deanonymization_failed`
