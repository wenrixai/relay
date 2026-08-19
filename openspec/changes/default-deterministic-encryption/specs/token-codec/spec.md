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

#### Scenario: IV uniqueness in random-IV mode
- **WHEN** the same plaintext is encrypted many times with the deterministic mode explicitly
  disabled
- **THEN** every token differs (random 96-bit IV; no ciphertext-equality correlation)

#### Scenario: Default mode sets the deterministic bit
- **WHEN** a value is encrypted without specifying a mode
- **THEN** the emitted token's control byte has bit 5 set and the reserved bits clear

### Requirement: Deterministic encryption mode
The codec SHALL encrypt in deterministic mode **by default**, using AES-256-SIV (RFC 5297)
with no nonce under the `K_siv` key, signaled by control-byte bit 5. In deterministic mode
the same plaintext SHALL always produce the identical token. Callers SHALL be able to opt
out per call and select the random-IV AES-256-CTR mode under `K_enc`, which leaves bit 5
clear. Decryption SHALL route on the deterministic flag — both modes decrypt through the
same `decrypt` entry point with no rule or configuration knowledge — and SHALL fail with a
typed error when the SIV tag does not authenticate. smaz compress-if-smaller SHALL apply in
deterministic mode exactly as in the random-IV mode.

Deterministic tokens are equality-comparable without the key. That equality SHALL be treated
as an accepted, documented disclosure of the *default* redaction path, not as a per-rule
exception: an observer of two redacted responses can learn that two fields hold the same
plaintext without learning the plaintext. Rules whose fields must not be correlatable SHALL
opt out explicitly.

#### Scenario: Deterministic tokens are equal
- **WHEN** the same plaintext is encrypted twice in deterministic mode
- **THEN** the two tokens are byte-identical

#### Scenario: Deterministic is the default
- **WHEN** a value is encrypted with no mode argument supplied
- **THEN** deterministic AES-SIV is used and repeating the call yields the identical token

#### Scenario: Random-IV mode reachable by opt-out
- **WHEN** a caller explicitly disables deterministic mode
- **THEN** AES-256-CTR under `K_enc` is used, bit 5 stays clear, and repeated calls differ

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
