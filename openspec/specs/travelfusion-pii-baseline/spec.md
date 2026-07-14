# travelfusion-pii-baseline Specification

## Purpose
Define the baked, sanitized Travelfusion booking PII baseline and its fail-closed schema-drift anchors.
## Requirements
### Requirement: Travelfusion booking-detail required anchor

The baked Travelfusion PII baseline SHALL mark `travelfusion.booking.traveller_name` as
`required: true` for both `GetBookingDetails` and `GetLatestBookingDetails`. This passenger-name
anchor SHALL ensure schema drift which prevents the baseline from locating the core traveller
structure fails closed instead of forwarding an apparently covered but unredacted response. The
ruleset version SHALL be bumped whenever this baseline changes.

#### Scenario: Travelfusion traveller-name anchor matches
- **WHEN** a supported booking-detail response contains the traveller-name structure targeted by
  `travelfusion.booking.traveller_name`
- **THEN** at least one traveller name is rewritten and response redaction continues

#### Scenario: Travelfusion schema drift fails closed
- **WHEN** the traveller-name element is removed or renamed so the required XPath rewrites no value
- **THEN** redaction raises and the relay returns 502 `pii_redaction_failed` with none of the
  upstream body

### Requirement: Travelfusion baseline uses sanitized golden evidence

The required anchor SHALL be exercised by sanitized Travelfusion fixtures in rule-level and
relay-level tests. Tests SHALL prove redaction/reversibility for normal booking-detail payloads and
fail-closed behavior for a drifted payload without making network calls or storing real passenger
data.

#### Scenario: Travelfusion golden baseline passes
- **WHEN** the Travelfusion PII suite runs against the baked ruleset and sanitized booking fixture
- **THEN** the required anchor rewrites traveller data and encrypted values round-trip
