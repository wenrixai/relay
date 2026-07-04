# pii-rules Specification Delta

## MODIFIED Requirements

### Requirement: Rule schema via pydantic discriminated actions
PII `field` rules SHALL support optional `extract_patterns`, a list of strict objects each carrying
a compilable `pattern` regex. Regexes SHALL validate at ruleset load time and SHALL be compiled once,
not per request. If an extraction regex has exactly one capture group, that group's span is the PII
span; otherwise the full match span is the PII span. `field` rules SHALL also support `required`
with default `false`. The public wire names remain `method` for the action and `operation` for the
channel operation matcher.

#### Scenario: Extract pattern loads
- **WHEN** a `field` rule declares `extract_patterns: [{"pattern": "..."}]`
- **THEN** validation succeeds and the compiled extraction regex is available to the engine

#### Scenario: Bad extract pattern rejected
- **WHEN** any extract pattern is not a compilable regex
- **THEN** the entire ruleset is invalid at load time

#### Scenario: Required defaults false
- **WHEN** a `field` rule omits `required`
- **THEN** the rule loads with `required` set to `false`

#### Scenario: Generated schema documents extraction and required
- **WHEN** the JSON Schema is generated from the rule models
- **THEN** it includes `extract_patterns`, `pattern`, and `required`
