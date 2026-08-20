# redaction-engine Specification

## Purpose
Define structural response redaction, request de-anonymization, and fail-closed PII processing.
## Requirements
### Requirement: Response redaction

For channels with `pii.enabled: true`, the relay SHALL redact XML/SOAP channel responses before
returning them to the client. Field rules select values by XPath, collect plaintext before rewriting,
and apply their configured action. Reference rules then replace occurrences of collected values in
their XPath-selected targets. The relay SHALL re-serialize once, preserving structure, namespaces,
and declarations. Channels without PII enabled SHALL pass through untouched. Unsupported inspected
content follows the `transparent-relay` fail-closed contract; rules cannot request a non-XPath path.

#### Scenario: Travelfusion wrapper operation parsed by handler
- **WHEN** a PII-enabled Travelfusion route returns `<CommandList><GetBookingDetails>...`
- **THEN** rule selection uses channel `travelfusion` and operation `GetBookingDetails`

#### Scenario: Travelfusion PII is reversible
- **WHEN** Travelfusion PII rules match passenger, contact, billing, address, or payment fields
- **THEN** every matched value is replaced with an `ENC_` token and decrypts back to the original value

#### Scenario: Golden redaction
- **WHEN** a PII-enabled channel returns an XML fixture with rule-matched fields
- **THEN** those fields are replaced per action and encrypted values decrypt to the originals

#### Scenario: Free-text reference redaction after collection
- **WHEN** a field rule collects person values and a reference rule targets free text containing them
- **THEN** the references and structured fields are redacted in the same pass

#### Scenario: Ignored pattern skipped
- **WHEN** a located node's text matches an `ignored_content_patterns` entry
- **THEN** that value is left unmodified

#### Scenario: Unknown namespace prefix is a no-match
- **WHEN** a rule XPath uses a namespace prefix absent from its declarations
- **THEN** the rule-path error counter increments, a safe warning is emitted, and processing
  continues unless the rule is required

#### Scenario: PII disabled passes through
- **WHEN** a channel without `pii.enabled` returns a response containing PII
- **THEN** the body is relayed byte-identical

#### Scenario: force_redact substitutes a fixed placeholder
- **WHEN** an encrypt rule matches on a channel with `pii.force_redact: true`
- **THEN** the value becomes the fixed `REDACTED` placeholder without consulting a keyring

#### Scenario: force_redact channel needs no keyring
- **WHEN** the only PII-enabled channel uses `pii.force_redact: true`
- **THEN** response redaction succeeds without `RELAY_PII_KEYRING`

### Requirement: Request de-anonymization

For channels with `pii.enabled: true`, the relay SHALL de-anonymize requests envelope-driven (no
rules required): parse the XML, scan text and attribute values for `ENC_` tokens — matching each
occurrence of the token contract (`TOKEN_RE`) whether it constitutes the entire value or is embedded
within surrounding free text — decode and decrypt each via the keyring (smaz-decompress when
flagged), splice the plaintext over each successfully decrypted span, re-serialize, and forward.
Every token that decrypts is delivered to the channel as plaintext; a failed embedded span is left
unchanged per the shape-based failure semantics below.

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

### Requirement: Channel-aware operation parsing

The relay SHALL parse the operation from the body using the configured channel handler when channel
context is available. The generic fallback SHALL use the SOAP Body's first child local-name, or the
document root local-name for non-SOAP XML. Operations SHALL never be taken from client headers.

#### Scenario: SOAP operation parsed
- **WHEN** a SOAP request's Body contains `<ns:PNR_Retrieve>`
- **THEN** the parsed operation is `PNR_Retrieve`

#### Scenario: Handler parses wrapped operation
- **WHEN** a channel-specific handler recognizes an operation below a wrapper element
- **THEN** rule selection uses the handler-derived operation

#### Scenario: Header ignored
- **WHEN** a client supplies an operation-naming header contradicting the body
- **THEN** rule selection uses only the body-derived operation

### Requirement: Intra-pass token reuse
Within a single response-redaction pass the relay SHALL maintain a plaintext→token cache so that
encrypting the same exact plaintext under the same encryption mode yields the same `ENC_` token
everywhere it occurs in that response — across repeated field-rule matches and reference-rule hits
alike. The cache SHALL be keyed on the exact plaintext plus the action's deterministic flag (tokens
are never shared between deterministic and non-deterministic rules), SHALL live only for the
duration of the single redaction pass, and SHALL NOT be persisted, logged, or shared across
requests or documents. Redaction counts SHALL count every rewritten occurrence, including
cache-served ones.

The cache remains a per-pass structure even though the default encryption mode is deterministic and
therefore already stable across passes: the cache SHALL NOT be widened, persisted, or keyed on
anything beyond `(plaintext, deterministic)`. Cross-response token stability is a property of the
cipher mode, never of retained relay state.

#### Scenario: Repeated field value shares one token
- **WHEN** two nodes matched by encrypt field rules in one response hold the identical plaintext
- **THEN** both are rewritten to the same `ENC_` token, and it decrypts to that plaintext

#### Scenario: Distinct values get distinct tokens
- **WHEN** two nodes hold different plaintexts
- **THEN** their tokens differ

#### Scenario: No cross-response reuse in random-IV mode
- **WHEN** the same plaintext appears in two separate responses redacted by encrypt rules that set
  `deterministic: false`
- **THEN** the two responses carry different tokens (the cache does not outlive a pass)

#### Scenario: Cross-response stability in the default mode
- **WHEN** the same plaintext appears in two separate responses redacted by encrypt rules that do
  not opt out of deterministic mode, under an unchanged master key
- **THEN** both responses carry the identical token, produced by the cipher mode rather than by any
  retained cache

#### Scenario: Mode isolation
- **WHEN** a deterministic encrypt rule and a non-deterministic encrypt rule both match the same
  plaintext in one response
- **THEN** the deterministic rule's nodes and the non-deterministic rule's nodes carry different
  tokens, each valid for decryption

### Requirement: Required rules prevent silent schema drift

For each selected field rule with `required: true`, the engine SHALL require at least one rewritten
value after XPath selection, ignored-pattern filtering, and extraction matching. An unsatisfied
required rule SHALL raise a redaction failure before any response is returned; the forwarder SHALL
map it to 502 `pii_redaction_failed` and SHALL return none of the upstream body.

#### Scenario: Required XPath no longer matches
- **WHEN** supplier schema drift renames or removes the node targeted by a selected required rule
- **THEN** the client receives 502 `pii_redaction_failed` and none of the upstream response body

### Requirement: XPath evaluation errors are observable and safe

The engine SHALL report every XPath evaluation error through an optional rule-path error callback
carrying only configured channel and rule ID. It SHALL emit a safe warning with the same identifiers
and SHALL NOT include payload values, XPath-selected content, tokens, credentials, or key material.
A non-required rule error SHALL remain a no-match and processing SHALL continue; a required rule
error SHALL subsequently fail because the rule is unsatisfied.

#### Scenario: Non-required XPath error continues
- **WHEN** a non-required rule XPath cannot be evaluated
- **THEN** the error is counted and warned, the rule rewrites nothing, and other rules continue

#### Scenario: Required XPath error fails closed
- **WHEN** a required rule XPath cannot be evaluated
- **THEN** the error is counted and the unsatisfied required rule fails the full redaction pass
