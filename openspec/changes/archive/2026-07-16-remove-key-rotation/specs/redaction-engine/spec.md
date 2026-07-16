## MODIFIED Requirements

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
