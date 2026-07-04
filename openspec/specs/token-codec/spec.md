# token-codec Specification

## Purpose
TBD - created by archiving change slice-2-pii-core. Update Purpose after archive.
## Requirements
### Requirement: Token format
PII tokens SHALL be encoded as `ENC_ + base64url_nopad(control ‖ iv ‖ ciphertext)` where `control`
is 1 byte (bits 0–3 key epoch, bit 4 compressed flag, bits 5–7 reserved as zero), `iv` is 12 random
bytes (96-bit), and `ciphertext` is AES-256-CTR of the payload under `K_enc[epoch]` with counter
`iv ‖ 0x00000000`. Tokens SHALL match `^ENC_[A-Za-z0-9_-]+$`. The format is confidentiality-only in
v1 and versioned via the reserved control bits.

#### Scenario: Round-trip
- **WHEN** any unicode string is encrypted and the token decrypted with the same keyring
- **THEN** the original string is recovered exactly

#### Scenario: Token matches contract regex
- **WHEN** any value is encrypted
- **THEN** the resulting token matches `^ENC_[A-Za-z0-9_-]+$`

#### Scenario: IV uniqueness
- **WHEN** the same plaintext is encrypted many times
- **THEN** every token differs (random 96-bit IV; no ciphertext-equality correlation)

### Requirement: smaz compress-if-smaller
The codec SHALL smaz-compress the plaintext before encryption and use the compressed form only when
it is strictly smaller, recording the choice in the control byte's compressed flag. Decryption SHALL
decompress only when the flag is set.

#### Scenario: Compressible text flagged
- **WHEN** a plaintext whose smaz output is smaller is encrypted
- **THEN** the control byte has the compressed flag set and round-trip recovers the plaintext

#### Scenario: Incompressible text stored raw
- **WHEN** a plaintext whose smaz output is not smaller (e.g. non-ASCII) is encrypted
- **THEN** the compressed flag is clear and round-trip recovers the plaintext

#### Scenario: Size bound
- **WHEN** any plaintext is encrypted
- **THEN** the token payload never exceeds the raw UTF-8 length plus the fixed 13-byte overhead
  (control + IV) before base64 expansion

### Requirement: Decode failure handling
Token decoding SHALL fail with a typed error (never a crash or silent pass-through) on: malformed
base64, truncated payload, unknown/absent epoch in the keyring, or nonzero reserved control bits.

#### Scenario: Unknown epoch fails
- **WHEN** a token references an epoch not present in the keyring
- **THEN** decoding raises a typed error identifying the epoch (never the key material)

#### Scenario: Truncated token fails
- **WHEN** a token's decoded payload is shorter than control + IV
- **THEN** decoding raises a typed error
