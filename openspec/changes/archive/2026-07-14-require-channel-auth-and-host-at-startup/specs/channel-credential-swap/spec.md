## ADDED Requirements

### Requirement: Credential configuration validation for all swap-enabled channels
When credential swap is enabled for a channel, the relay SHALL validate at configuration load that the
credential fields its handler requires are present and well-formed, for **every** channel type that
performs a swap — Travelfusion, Farelogix (AA/LH/UA/EK), the NDC header channels (BA/LA), and the SOAP
(Amadeus/Sabre) and Travelport channels. Validation failure SHALL abort startup with an error that
identifies the channel and the invalid condition and contains no credential value. A channel with
`credentials.enabled=false` SHALL require no credentials.

This generalizes the existing Travelport/SOAP load-time validation to the remaining swap handlers, so
that an incomplete credential set can never boot ready and then fail every request at swap time with
`credential_swap_failed`.

#### Scenario: Incomplete Farelogix credentials rejected at load
- **WHEN** an enabled Farelogix channel omits a required field (e.g. `password` or an agent field)
- **THEN** configuration loading aborts before the relay accepts traffic, naming the channel

#### Scenario: Missing NDC API key rejected at load
- **WHEN** an enabled BA/LA NDC channel omits its required API-key credential
- **THEN** configuration loading aborts before the relay accepts traffic, naming the channel

#### Scenario: Incomplete Travelfusion credentials rejected at load
- **WHEN** an enabled Travelfusion channel omits a required login field
- **THEN** configuration loading aborts before the relay accepts traffic, naming the channel

#### Scenario: Disabled swap needs no credentials
- **WHEN** a swap-capable channel has `credentials.enabled=false`
- **THEN** configuration loading does not require its credential fields
