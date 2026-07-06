## MODIFIED Requirements

### Requirement: Epoch-indexed keyring
The relay SHALL load a PII master keyring of the form `{epoch_int: base64(32 bytes)}` from the
`RELAY_PII_KEYRING` setting (inline JSON) or a mounted secret file (file takes precedence when both
are set). Epochs MUST be integers in the range 0–15 (the token control byte carries 4 epoch bits);
keys MUST decode to exactly 32 bytes. Invalid keyring material SHALL abort startup when any channel
has `pii.enabled: true` and `pii.force_redact` is not also true, or when any channel's credentials
require a response-auth keyring. A channel with `pii.enabled: true` and `pii.force_redact: true`
SHALL NOT, by itself, require a configured keyring.

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
- **WHEN** a channel sets `pii.enabled: true` (and `pii.force_redact` is false or unset) and no
  keyring is configured
- **THEN** startup aborts with a clear error (readiness never reached)

#### Scenario: force_redact-only channel does not require a keyring
- **WHEN** the only channel with `pii.enabled: true` also has `pii.force_redact: true`, no other
  channel's credentials require a response-auth keyring, and no keyring is configured
- **THEN** startup succeeds and readiness is reached
