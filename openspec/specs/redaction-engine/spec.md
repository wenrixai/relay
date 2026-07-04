# redaction-engine Specification

## Purpose
TBD - created by archiving change slice-2-pii-core. Update Purpose after archive.
## Requirements
### Requirement: Response redaction
For channels with `pii.enabled: true`, the relay SHALL redact channel responses before returning
them to the client: parse the XML via the hardened factory, parse the operation from the body,
select rules where `channel` matches and the `operation` regex matches, locate nodes by XPath using
rule-declared namespaces, skip values matching `ignored_content_patterns`, apply the rule's action
(`encrypt` → `ENC_` token, `mask`, `replace`, `remove`), and re-serialize preserving structure,
namespaces, and declarations. Channels without PII enabled SHALL pass through untouched. Rules with
`path_type: jsonpath` are loaded but skipped in this slice.

#### Scenario: Golden redaction
- **WHEN** a PII-enabled channel returns a fixture response with rule-matched fields
- **THEN** the client receives the fixture with those fields replaced per each rule's action, and
  decrypting the `ENC_` tokens recovers the original values

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
rules required): parse the XML, scan text and attribute values for full-match `ENC_` tokens, decode
and decrypt each via the keyring (epoch from the control byte, smaz-decompress when flagged),
replace with plaintext, re-serialize, and forward. The channel always receives plaintext.

#### Scenario: Round-trip
- **WHEN** a value redacted from an earlier response is sent back as an `ENC_` token in a request
- **THEN** the channel receives the original plaintext value

#### Scenario: Non-token values untouched
- **WHEN** a request contains values that do not full-match the token regex
- **THEN** they are forwarded unmodified

### Requirement: Fail-closed error semantics
Any crypto, rule, or XML error during redaction or de-anonymization SHALL produce the 502 JSON
error contract (reason `pii_redaction_failed` or `pii_deanonymization_failed`) and the relay SHALL
never forward a partially processed body in either direction. Error details SHALL never contain
PII or key material.

#### Scenario: Redaction failure drops response
- **WHEN** encryption of a located field fails mid-document
- **THEN** the client receives 502 `pii_redaction_failed` and none of the upstream body

#### Scenario: Bad token blocks request
- **WHEN** a request token fails decoding or decryption
- **THEN** the channel receives nothing and the client gets 502 `pii_deanonymization_failed`

### Requirement: Generic operation parsing (interim)
Until per-channel parsers land (T3.2), the relay SHALL parse the operation from the body with a
generic XML parser: the SOAP Body's first child local-name, or the document root local-name for
non-SOAP XML. Operations SHALL never be taken from client headers.

#### Scenario: SOAP operation parsed
- **WHEN** a SOAP request's Body contains `<ns:PNR_Retrieve>`
- **THEN** the parsed operation is `PNR_Retrieve`

#### Scenario: Header ignored
- **WHEN** a client supplies an operation-naming header contradicting the body
- **THEN** rule selection uses only the body-derived operation
