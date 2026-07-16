## ADDED Requirements

### Requirement: Single master keyring
The relay SHALL load a single PII master key from the `RELAY_PII_KEYRING` setting (inline)
or a mounted secret file (file takes precedence when both are set). The source SHALL be a
base64 string that decodes to exactly 32 bytes. For backward compatibility with
already-provisioned secrets, a legacy JSON object with exactly the single entry
(`{"0": "<base64 32B>"}`) SHALL also be accepted, using that key; a JSON object with more
than one entry, or with a single entry under any key other than `"0"`, SHALL be rejected
with a validation error indicating that key rotation has been removed. Invalid keyring
material SHALL abort startup when any channel has
`pii.enabled: true` and `pii.force_redact` is not also true, or when any channel's
credentials require a response-auth keyring. A channel with `pii.enabled: true` and
`pii.force_redact: true` SHALL NOT, by itself, require a configured keyring.

#### Scenario: Bare base64 key loads
- **WHEN** the keyring source is a base64 string decoding to 32 bytes
- **THEN** the keyring loads and exposes derived encryption keys

#### Scenario: Legacy single-entry object loads
- **WHEN** the keyring source is `{"0": "<base64 32B>"}`
- **THEN** the keyring loads using that key

#### Scenario: Multi-entry object rejected
- **WHEN** the keyring source is a JSON object with more than one entry
- **THEN** keyring loading fails with a validation error stating rotation was removed

#### Scenario: Single non-zero-key object rejected
- **WHEN** the keyring source is a single-entry object under a key other than `"0"` (e.g. `{"5": "<base64 32B>"}`)
- **THEN** keyring loading fails with a validation error (its outstanding tokens would fail closed)

#### Scenario: Wrong key length rejected
- **WHEN** the key decodes to a length other than 32 bytes
- **THEN** keyring loading fails with a validation error

#### Scenario: PII enabled without keyring aborts startup
- **WHEN** a channel sets `pii.enabled: true` (and `pii.force_redact` is false or unset) and no
  keyring is configured
- **THEN** startup aborts with a clear error (readiness never reached)

#### Scenario: force_redact-only channel does not require a keyring
- **WHEN** the only channel with `pii.enabled: true` also has `pii.force_redact: true`, no other
  channel's credentials require a response-auth keyring, and no keyring is configured
- **THEN** startup succeeds and readiness is reached

## MODIFIED Requirements

### Requirement: HKDF key derivation
The relay SHALL derive two keys from the master key using HKDF-SHA256 with fixed, distinct
domain-separation info strings: the 32-byte field-encryption key `K_enc` (existing info
label) and the 64-byte deterministic-encryption key `K_siv` (a distinct `siv` info label,
sized for AES-256-SIV). The master key SHALL never be used directly as a cipher key, and no
derived or master key material SHALL ever be logged. Rotating the master key rotates both
derived keys.

#### Scenario: Derivation is deterministic
- **WHEN** the same master key is loaded twice
- **THEN** the derived `K_enc` and `K_siv` are identical across loads

#### Scenario: Domain separation between derived keys
- **WHEN** `K_enc` and `K_siv` are derived from the same master key
- **THEN** neither is a prefix of or equal to the other (distinct HKDF info labels)

## REMOVED Requirements

### Requirement: Epoch-indexed keyring
**Reason**: Key rotation via the 1-byte epoch is removed; rotation will be reintroduced
later through a KMS store plugin. The keyring is now a single master key (see the added
"Single master keyring" requirement).
**Migration**: Provide a single base64(32-byte) key as the keyring source. Existing
single-entry `{"0": "<base64>"}` secrets remain accepted; multi-entry keyrings are no longer
supported and are rejected at startup.

### Requirement: Active epoch selection
**Reason**: With a single master key there is no active-epoch concept; new tokens always
encrypt under the sole key.
**Migration**: Remove `RELAY_PII_KEY_EPOCH_ACTIVE` from configuration. All tokens encrypt
and decrypt under the single loaded key.
