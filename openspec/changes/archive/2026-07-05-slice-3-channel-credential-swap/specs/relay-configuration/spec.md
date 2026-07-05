## MODIFIED Requirements

### Requirement: Pydantic-first configuration

The relay SHALL express all configuration as pydantic v2 models as the single source of truth, and
SHALL generate the JSON Schema from those models (never hand-maintained). Per-channel `credentials`
SHALL be a string map whose keys are interpreted by the selected channel handler. Empty credentials
SHALL be valid and SHALL disable credential swap.

#### Scenario: Credential map accepted
- **WHEN** a channel config provides credential keys for its channel type
- **THEN** the model validates and the handler can read those values during forwarding
