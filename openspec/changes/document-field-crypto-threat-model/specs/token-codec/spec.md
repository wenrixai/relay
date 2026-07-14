## MODIFIED Requirements

### Requirement: Token format
PII tokens SHALL be encoded as `ENC_ + base64url_nopad(control ‖ body)` where `control` is 1 byte
(bits 0–3 key epoch, bit 4 compressed flag, bit 5 deterministic flag, bits 6–7 reserved as zero) and
`body` depends on the deterministic flag: when clear, `body = iv ‖ ciphertext` with `iv` 12 random
bytes (96-bit) and `ciphertext` AES-256-CTR of the payload under `K_enc[epoch]` with counter
`iv ‖ 0x00000000`; when set, `body` is the AES-256-SIV (RFC 5297, no nonce) encryption of the payload
under `K_siv[epoch]` (16-byte synthetic IV/tag followed by ciphertext). Tokens SHALL match
`^ENC_[A-Za-z0-9_-]+$`.

The default random-IV CTR form is **confidentiality-only and provides no integrity or tamper
protection**: a modified ciphertext may decrypt to a different plaintext without detection, and the
codec does not authenticate it. Only the deterministic SIV mode is authenticated (its synthetic IV
doubles as a tag). This is an accepted v1 property under the threat model (a party *reading* the XML,
with TLS providing transport integrity), not a party tampering with stored tokens. The format remains
versioned via the reserved control bits, so an authenticated (AEAD) default mode MAY be added later
without breaking existing tokens. Deployments that must resist token tampering SHOULD use the
deterministic mode for the affected rules or await the AEAD default.

#### Scenario: Round-trip
- **WHEN** any unicode string is encrypted and the token decrypted with the same keyring
- **THEN** the original string is recovered exactly

#### Scenario: Token matches contract regex
- **WHEN** any value is encrypted
- **THEN** the resulting token matches `^ENC_[A-Za-z0-9_-]+$`

#### Scenario: IV uniqueness in default mode
- **WHEN** the same plaintext is encrypted many times in the default (non-deterministic) mode
- **THEN** every token differs (random 96-bit IV; no ciphertext-equality correlation)

#### Scenario: Default mode is documented as non-authenticated
- **WHEN** the token format is described in the spec/security docs
- **THEN** it states the default CTR mode provides no integrity and names the deterministic SIV mode
  as the authenticated option
