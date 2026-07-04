# crypto-keyring Specification

## Purpose
TBD - created by archiving change slice-2-pii-core. Update Purpose after archive.
## Requirements
### Requirement: Epoch-indexed keyring
The relay SHALL load a PII master keyring of the form `{epoch_int: base64(32 bytes)}` from the
`RELAY_PII_KEYRING` setting (inline JSON) or a mounted secret file (file takes precedence when both
are set). Epochs MUST be integers in the range 0–15 (the token control byte carries 4 epoch bits);
keys MUST decode to exactly 32 bytes. Invalid keyring material SHALL abort startup when any channel
has `pii.enabled: true`.

#### Scenario: Valid keyring loads
- **WHEN** the keyring source contains `{"0": "<base64 32B>", "1": "<base64 32B>"}`
- **THEN** the keyring exposes epochs 0 and 1 with derived encryption keys

#### Scenario: Epoch out of range rejected
- **WHEN** the keyring source contains epoch `16` or a negative epoch
- **THEN** keyring loading fails with a validation error

#### Scenario: Wrong key length rejected
- **WHEN** a keyring entry decodes to a length other than 32 bytes
- **THEN** keyring loading fails with a validation error

#### Scenario: PII enabled without keyring aborts startup
- **WHEN** a channel sets `pii.enabled: true` and no keyring is configured
- **THEN** startup aborts with a clear error (readiness never reached)

### Requirement: HKDF key derivation
The relay SHALL derive the field-encryption key `K_enc[epoch]` from each epoch's master key using
HKDF-SHA256 with a fixed domain-separation info string. Master keys SHALL never be used directly as
cipher keys, and no derived or master key material SHALL ever be logged.

#### Scenario: Derivation is deterministic
- **WHEN** the same master key and epoch are loaded twice
- **THEN** the derived `K_enc` is identical

#### Scenario: Different epochs derive different keys
- **WHEN** two epochs hold different master keys
- **THEN** their derived `K_enc` values differ

### Requirement: Active epoch selection
The relay SHALL encrypt new tokens with the epoch given by `RELAY_PII_KEY_EPOCH_ACTIVE`, defaulting
to the highest epoch present in the keyring. All loaded epochs SHALL remain available for
decryption (rotation keeps old tokens readable).

#### Scenario: Default active epoch is highest
- **WHEN** the keyring holds epochs 0 and 3 and no active epoch is configured
- **THEN** new encryptions use epoch 3

#### Scenario: Configured active epoch missing from keyring
- **WHEN** `RELAY_PII_KEY_EPOCH_ACTIVE` names an epoch not present in the keyring
- **THEN** startup aborts with a validation error

#### Scenario: Old epoch still decrypts
- **WHEN** a token was encrypted under epoch 0 and the active epoch is now 1
- **THEN** decryption with the keyring succeeds using epoch 0's key
