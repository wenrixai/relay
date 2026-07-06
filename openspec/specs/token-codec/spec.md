# token-codec Specification

## Purpose
TBD - created by archiving change slice-2-pii-core. Update Purpose after archive.
## Requirements
### Requirement: Token format
PII tokens SHALL be encoded as `ENC_ + base64url_nopad(control ‖ body)` where `control` is 1 byte
(bits 0–3 key epoch, bit 4 compressed flag, bit 5 deterministic flag, bits 6–7 reserved as zero) and
`body` depends on the deterministic flag: when clear, `body = iv ‖ ciphertext` with `iv` 12 random
bytes (96-bit) and `ciphertext` AES-256-CTR of the payload under `K_enc[epoch]` with counter
`iv ‖ 0x00000000`; when set, `body` is the AES-256-SIV (RFC 5297, no nonce) encryption of the
payload under `K_siv[epoch]` (16-byte synthetic IV/tag followed by ciphertext). Tokens SHALL match
`^ENC_[A-Za-z0-9_-]+$`. The random-IV CTR form is confidentiality-only; the format remains versioned
via the remaining reserved control bits.

#### Scenario: Round-trip
- **WHEN** any unicode string is encrypted and the token decrypted with the same keyring
- **THEN** the original string is recovered exactly

#### Scenario: Token matches contract regex
- **WHEN** any value is encrypted
- **THEN** the resulting token matches `^ENC_[A-Za-z0-9_-]+$`

#### Scenario: IV uniqueness in default mode
- **WHEN** the same plaintext is encrypted many times in the default (non-deterministic) mode
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

### Requirement: Deterministic encryption mode
The codec SHALL offer an opt-in deterministic encryption mode using AES-256-SIV (RFC 5297) with no
nonce under the per-epoch `K_siv` key, signaled by control-byte bit 5. In deterministic mode the
same plaintext under the same active epoch SHALL always produce the identical token. Decryption
SHALL route on the deterministic flag — both modes decrypt through the same `decrypt` entry point
with no rule or configuration knowledge — and SHALL fail with a typed error when the SIV tag does
not authenticate. smaz compress-if-smaller SHALL apply in deterministic mode exactly as in the
default mode. Non-deterministic (random-IV CTR) SHALL remain the default mode.

#### Scenario: Deterministic tokens are equal
- **WHEN** the same plaintext is encrypted twice in deterministic mode under the same active epoch
- **THEN** the two tokens are byte-identical

#### Scenario: Deterministic round-trip
- **WHEN** a plaintext is encrypted in deterministic mode and the token decrypted with the same keyring
- **THEN** the original string is recovered exactly and no mode hint is needed by the caller

#### Scenario: Different plaintexts differ
- **WHEN** two different plaintexts are encrypted in deterministic mode
- **THEN** the tokens differ

#### Scenario: Epoch rotation changes deterministic tokens
- **WHEN** the active epoch changes and the same plaintext is encrypted deterministically
- **THEN** the token differs from the previous epoch's token, and both decrypt correctly

#### Scenario: Tampered deterministic token fails closed
- **WHEN** a deterministic token's ciphertext is modified and decryption is attempted
- **THEN** decoding raises a typed error (SIV authentication failure), never returns garbage plaintext

#### Scenario: Legacy tokens unaffected
- **WHEN** a token minted before this change (deterministic bit clear) is decrypted
- **THEN** it decrypts exactly as before; bits 6–7 set still raise the reserved-bits typed error
