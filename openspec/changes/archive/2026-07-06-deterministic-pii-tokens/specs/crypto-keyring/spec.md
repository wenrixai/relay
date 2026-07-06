## MODIFIED Requirements

### Requirement: HKDF key derivation
The relay SHALL derive two keys from each epoch's master key using HKDF-SHA256 with fixed,
distinct domain-separation info strings: the 32-byte field-encryption key `K_enc[epoch]` (existing
info label) and the 64-byte deterministic-encryption key `K_siv[epoch]` (a distinct `siv` info
label, sized for AES-256-SIV). Master keys SHALL never be used directly as cipher keys, and no
derived or master key material SHALL ever be logged. Keyring format, epoch semantics, and rotation
behavior are unchanged — rotating a master key rotates both derived keys.

#### Scenario: Derivation is deterministic
- **WHEN** the same master key and epoch are loaded twice
- **THEN** the derived `K_enc` and `K_siv` are identical across loads

#### Scenario: Different epochs derive different keys
- **WHEN** two epochs hold different master keys
- **THEN** their derived `K_enc` values differ and their derived `K_siv` values differ

#### Scenario: Domain separation between derived keys
- **WHEN** `K_enc` and `K_siv` are derived from the same master key
- **THEN** neither is a prefix of or equal to the other (distinct HKDF info labels)

#### Scenario: Unknown epoch fails for SIV key
- **WHEN** `K_siv` is requested for an epoch not present in the keyring
- **THEN** the same typed unknown-epoch error is raised as for `K_enc`
