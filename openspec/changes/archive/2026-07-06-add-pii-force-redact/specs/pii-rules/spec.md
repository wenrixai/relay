## MODIFIED Requirements

### Requirement: Rule schema via pydantic discriminated actions
PII rules SHALL be modeled in pydantic v2 with strict validation (`extra="forbid"`). A ruleset
carries `schema_version`, `rules_version`, and `rules[]`. Each field rule carries `id`, `channel`,
`operation` (compilable regex), `path`, `path_type` (`xpath` default | `jsonpath`), `pii_type`, an
action, and optional `ignored_content_patterns` (each a compilable regex). Actions SHALL form a
discriminated union on `method`: `encrypt` (no params), `mask` (`mask_char`, `keep_prefix`),
`replace` (`replacement` required), `remove` (no params). Each rule MAY declare `namespaces`
(prefix → URI) used to evaluate its XPath; a prefix used in `path` but not declared is a
no-match at evaluation time, never an error. The wire format stays flat (§8.1 style:
`method` plus its params at rule level). The rules JSON Schema SHALL be generated from the models,
never hand-written. A channel's `pii.force_redact` config (see `relay-configuration`) MAY override
the effective outcome of an `encrypt` action at apply time without changing the rule's stored
`method` — the rules document itself is unaffected by this override.

#### Scenario: Valid encrypt rule loads
- **WHEN** a rule provides id/channel/operation/path/pii_type with `method: encrypt`
- **THEN** validation succeeds and the action resolves to the encrypt variant

#### Scenario: Replace without replacement rejected
- **WHEN** a rule sets `method: replace` without `replacement`
- **THEN** validation fails naming the missing parameter

#### Scenario: Unknown method rejects ruleset
- **WHEN** any rule carries an unrecognized `method`
- **THEN** the entire ruleset is invalid (fail closed; no partial acceptance)

#### Scenario: Bad regex rejected at load
- **WHEN** `operation` or an `ignored_content_patterns` entry is not a compilable regex
- **THEN** validation fails at load time (never at request time)

#### Scenario: Generated schema documents actions
- **WHEN** the JSON Schema is generated from the rule models
- **THEN** it encodes the method discriminator and per-method required parameters

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
hand-written, and SHALL encode the `rule_type` discriminator and per-kind required parameters. As
with `field` rules, a channel's `pii.force_redact` config MAY override a reference rule's `encrypt`
outcome to the fixed `"REDACTED"` literal at apply time (see `referential-redaction`); the rule's
stored `action` remains `encrypt` regardless.

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
