## MODIFIED Requirements

### Requirement: PII key provisioning survives upgrade
The chart SHALL provision the PII master-key Secret create-if-absent and SHALL NOT
regenerate it on `helm upgrade`; all pods SHALL mount the same Secret at the keyring file
path wired to `RELAY_PII_KEYRING_FILE`. The generated Secret SHALL contain a single
base64(32-byte) master key and SHALL NOT reference key epochs or an active-epoch value.

#### Scenario: Upgrade does not regenerate the key
- **WHEN** the chart is upgraded and a master-key Secret already exists
- **THEN** the existing Secret is preserved and no new master key is generated

#### Scenario: Rendered Secret carries no epoch fields
- **WHEN** the chart is rendered with `helm template`
- **THEN** neither the Secret nor the Deployment references `RELAY_PII_KEY_EPOCH_ACTIVE` or
  a `piiKeyring.activeEpoch` value
