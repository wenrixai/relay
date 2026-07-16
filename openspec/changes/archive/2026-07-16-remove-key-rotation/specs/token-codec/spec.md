## MODIFIED Requirements

### Requirement: Token format
PII tokens SHALL be encoded as `ENC_ + base64url_nopad(control ‖ body)` where `control` is 1
byte (bit 4 compressed flag, bit 5 deterministic flag, bits 0–3 and 6–7 reserved as zero)
and `body` depends on the deterministic flag: when clear, `body = iv ‖ ciphertext` with `iv`
12 random bytes (96-bit) and `ciphertext` AES-256-CTR of the payload under `K_enc` with
counter `iv ‖ 0x00000000`; when set, `body` is the AES-256-SIV (RFC 5297, no nonce)
encryption of the payload under `K_siv` (16-byte synthetic IV/tag followed by ciphertext).
Encryption SHALL write the reserved bits (0–3 and 6–7) as zero. Tokens SHALL match
`^ENC_[A-Za-z0-9_-]+$`. The random-IV CTR form is confidentiality-only; the format remains
versioned via the reserved control bits.

#### Scenario: Round-trip
- **WHEN** any unicode string is encrypted and the token decrypted with the same keyring
- **THEN** the original string is recovered exactly

#### Scenario: Token matches contract regex
- **WHEN** any value is encrypted
- **THEN** the resulting token matches `^ENC_[A-Za-z0-9_-]+$`

#### Scenario: IV uniqueness in default mode
- **WHEN** the same plaintext is encrypted many times in the default (non-deterministic) mode
- **THEN** every token differs (random 96-bit IV; no ciphertext-equality correlation)

### Requirement: Decode failure handling
Token decoding SHALL fail with a typed error (never a crash or silent pass-through) on:
malformed base64, truncated payload, or any nonzero reserved control bits (bits 0–3 or 6–7).
The truncation check is mode-specific: a default-mode (CTR) body SHALL be at least the 12-byte
IV; a deterministic-mode (AES-SIV) body SHALL be at least the 16-byte SIV tag.

#### Scenario: Reserved bits fail
- **WHEN** a token's control byte has any reserved bit (0–3 or 6–7) set
- **THEN** decoding raises a typed error (unsupported/version) and never returns plaintext

#### Scenario: Truncated default-mode token fails
- **WHEN** a default-mode token's body is shorter than the 12-byte IV
- **THEN** decoding raises a typed error

#### Scenario: Truncated deterministic token fails
- **WHEN** a deterministic-mode token's body is shorter than the 16-byte SIV tag
- **THEN** decoding raises a typed error

### Requirement: Deterministic encryption mode
The codec SHALL offer an opt-in deterministic encryption mode using AES-256-SIV (RFC 5297)
with no nonce under the `K_siv` key, signaled by control-byte bit 5. In deterministic mode
the same plaintext SHALL always produce the identical token. Decryption SHALL route on the
deterministic flag — both modes decrypt through the same `decrypt` entry point with no rule
or configuration knowledge — and SHALL fail with a typed error when the SIV tag does not
authenticate. smaz compress-if-smaller SHALL apply in deterministic mode exactly as in the
default mode. Non-deterministic (random-IV CTR) SHALL remain the default mode.

#### Scenario: Deterministic tokens are equal
- **WHEN** the same plaintext is encrypted twice in deterministic mode
- **THEN** the two tokens are byte-identical

#### Scenario: Deterministic round-trip
- **WHEN** a plaintext is encrypted in deterministic mode and the token decrypted with the same keyring
- **THEN** the original string is recovered exactly and no mode hint is needed by the caller

#### Scenario: Different plaintexts differ
- **WHEN** two different plaintexts are encrypted in deterministic mode
- **THEN** the tokens differ

#### Scenario: Tampered deterministic token fails closed
- **WHEN** a deterministic token's ciphertext is modified and decryption is attempted
- **THEN** decoding raises a typed error (SIV authentication failure), never returns garbage plaintext

#### Scenario: Legacy tokens unaffected
- **WHEN** a token minted before this change with the deterministic bit clear and no reserved
  bits set is decrypted
- **THEN** it decrypts exactly as before; any reserved bit (0–3 or 6–7) set still raises the
  reserved-bits typed error
