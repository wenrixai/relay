## MODIFIED Requirements

### Requirement: Request de-anonymization

For channels with `pii.enabled: true`, the relay SHALL de-anonymize requests envelope-driven (no
rules required): parse the XML, scan text, **tail text**, and attribute values for `ENC_` tokens —
matching each occurrence of the token contract (`TOKEN_RE`) whether it constitutes the entire value
or is embedded within surrounding free text — decode and decrypt each via the keyring (epoch from the
control byte, smaz-decompress when flagged), splice the plaintext over each matched span, re-serialize,
and forward. The channel always receives plaintext. Text following a child element (lxml `.tail`) is
in scope: an `ENC_` token in mixed content SHALL NOT be forwarded to the channel undecrypted.

Failure semantics differ by shape: when a value (in text, tail, or an attribute) is EXACTLY one token
(`fullmatch`) and it fails to decode/decrypt, the relay SHALL fail closed (502
`pii_deanonymization_failed`, nothing forwarded); when a token is EMBEDDED among other text and that
span fails to decode/decrypt, the relay SHALL leave that span untouched and continue.

#### Scenario: Round-trip
- **WHEN** a value redacted from an earlier response is sent back as an `ENC_` token in a request
- **THEN** the channel receives the original plaintext value

#### Scenario: Tail-text token round-trip
- **WHEN** a request carries an `ENC_` token in mixed-content tail text (e.g. `<a/>ENC_…<b/>`)
- **THEN** the token is decrypted in place and the channel receives the tail text with the plaintext
  spliced back in

#### Scenario: Full-value bad token fails closed
- **WHEN** a value (text, tail, or attribute) is EXACTLY one `ENC_` token that fails decoding or
  decryption
- **THEN** the channel receives nothing and the client gets 502 `pii_deanonymization_failed`

### Requirement: Fail-closed error semantics
Any crypto, rule, or XML error during redaction or de-anonymization SHALL produce the 502 JSON error
contract (reason `pii_redaction_failed` or `pii_deanonymization_failed`) and the relay SHALL never
forward a partially processed body in either direction. Error details SHALL never contain field
values, tokens, or key material. The fail-closed guards that prevent calling the crypto codec without
a keyring SHALL be explicit runtime checks, not `assert` statements, so they remain effective under an
optimized interpreter (`python -O` / `PYTHONOPTIMIZE`).

#### Scenario: Fail closed on crypto error
- **WHEN** a token fails to encrypt/decrypt during a redaction or de-anonymization pass
- **THEN** the relay returns the 502 contract and forwards nothing

#### Scenario: Keyring guard holds under optimized interpreter
- **WHEN** an `encrypt` action is reached without a keyring on a non-`force_redact` channel while
  assertions are disabled
- **THEN** the relay fails closed via an explicit check (not an assertion) and forwards nothing
