## ADDED Requirements

### Requirement: Reference rule kind in the ruleset

The rule schema SHALL support a second rule kind discriminated on `rule_type`: `field` (the existing
kind, the implied default) and `reference`. A `reference` rule SHALL be modeled in pydantic v2 with
strict validation (`extra="forbid"`) and SHALL carry `id`, `channel`, `operation` (compilable
regex), `path`, `path_type` (`xpath` default | `jsonpath`), optional `namespaces` (prefix → URI),
`source_pii_types` (a non-empty list of `pii_type` values whose collected values it searches for),
`pii_type` (the type attributed to its redactions), match guards `min_match_len` (integer ≥ 1,
default 3) and `word_boundary` (bool, default true), and an `action`. In v1 the reference action
SHALL be `encrypt`. A `RuleSet.rules[]` SHALL accept a mixed list of `field` and `reference` rules,
discriminated on `rule_type`. The rules JSON Schema SHALL be generated from the models, never
hand-written, and SHALL encode the `rule_type` discriminator and per-kind required parameters.

#### Scenario: Valid reference rule loads
- **WHEN** a rule provides `rule_type: reference`, id/channel/operation/path, a non-empty
  `source_pii_types`, `pii_type`, and `method: encrypt`
- **THEN** validation succeeds and the rule resolves to the reference kind

#### Scenario: Empty source_pii_types rejected
- **WHEN** a `reference` rule declares an empty `source_pii_types`
- **THEN** validation fails naming the missing source types (fail closed at load time)

#### Scenario: Unknown source pii_type rejected
- **WHEN** `source_pii_types` contains a value outside the `pii_type` enumeration
- **THEN** the entire ruleset is invalid (no partial acceptance)

#### Scenario: Mixed ruleset loads
- **WHEN** a ruleset contains both `field` and `reference` rules
- **THEN** each rule is validated against its own kind's schema and the ruleset loads

#### Scenario: Bad regex in reference operation rejected at load
- **WHEN** a `reference` rule's `operation` is not a compilable regex
- **THEN** validation fails at load time, never at request time

#### Scenario: Generated schema documents the rule_type discriminator
- **WHEN** the JSON Schema is generated from the rule models
- **THEN** it encodes the `rule_type` discriminator and the reference kind's required parameters
