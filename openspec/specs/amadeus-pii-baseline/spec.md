# amadeus-pii-baseline Specification

## Purpose
Define the baked, sanitized Amadeus PNR PII baseline and its fail-closed schema-drift anchors.
## Requirements
### Requirement: Amadeus PNR required anchor

The baked Amadeus PII baseline SHALL mark `amadeus.pnr.surname` as `required: true` for
`PNR_Reply`. This passenger-name anchor SHALL ensure that schema drift which prevents the baseline
from locating the core PNR passenger structure fails closed instead of forwarding an apparently
covered but unredacted response. The ruleset version SHALL be bumped whenever this baseline changes.

#### Scenario: Amadeus surname anchor matches
- **WHEN** a supported `PNR_Reply` contains the passenger surname structure targeted by
  `amadeus.pnr.surname`
- **THEN** at least one surname is rewritten and response redaction continues

#### Scenario: Amadeus schema drift fails closed
- **WHEN** the passenger surname element is removed or renamed so the required XPath rewrites no value
- **THEN** redaction raises and the relay returns 502 `pii_redaction_failed` with none of the
  upstream body

### Requirement: Amadeus baseline uses sanitized golden evidence

The required anchor SHALL be exercised by sanitized Amadeus fixtures in rule-level and relay-level
tests. Tests SHALL prove redaction/reversibility for normal payloads and fail-closed behavior for a
drifted payload without making network calls or storing real passenger data.

#### Scenario: Amadeus golden baseline passes
- **WHEN** the Amadeus PII suite runs against the baked ruleset and sanitized `PNR_Reply` fixture
- **THEN** the required anchor rewrites passenger data and encrypted values round-trip
