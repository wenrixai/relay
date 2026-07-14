## MODIFIED Requirements

### Requirement: Active epoch selection
The relay SHALL encrypt new tokens with the epoch given by `RELAY_PII_KEY_EPOCH_ACTIVE`, defaulting to
the highest epoch present in the keyring. All loaded epochs SHALL remain available for decryption
(rotation keeps old tokens readable). Because the default token mode uses a random 96-bit IV, the
number of encryptions under a single epoch key SHALL be bounded well below the birthday limit at which
IV collision becomes non-negligible; the relay's operational documentation SHALL provide
**volume-based** epoch-rotation guidance (rotate to a new epoch before an epoch approaches that safe
encryption-count bound), in addition to any calendar-based rotation.

#### Scenario: Default active epoch is highest
- **WHEN** the keyring holds epochs 0 and 3 and no active epoch is configured
- **THEN** new encryptions use epoch 3

#### Scenario: Configured active epoch missing from keyring
- **WHEN** `RELAY_PII_KEY_EPOCH_ACTIVE` names an epoch not present in the keyring
- **THEN** startup aborts with a validation error

#### Scenario: Old epoch still decrypts
- **WHEN** a token was encrypted under epoch 0 and the active epoch is now 1
- **THEN** decryption with the keyring succeeds using epoch 0's key

#### Scenario: Rotation guidance is volume-aware
- **WHEN** the operational documentation describes epoch rotation
- **THEN** it states a volume-based rotation threshold keyed to the safe per-epoch encryption count,
  not only a calendar interval
