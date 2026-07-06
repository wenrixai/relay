## MODIFIED Requirements

### Requirement: Rule schema via pydantic discriminated actions
PII rules SHALL be modeled in pydantic v2 with strict validation (`extra="forbid"`). A ruleset
carries `schema_version`, `rules_version`, and `rules[]`. Each field rule carries `id`, `channel`,
`operation` (compilable regex), `path`, `path_type` (`xpath` default | `jsonpath`), `pii_type`, an
action, and optional `ignored_content_patterns` (each a compilable regex). Actions SHALL form a
discriminated union on `method`: `encrypt` (optional `deterministic` boolean, default `false`),
`mask` (`mask_char`, `keep_prefix`), `replace` (`replacement` required), `remove` (no params). The
`deterministic` flag SHALL be accepted on `encrypt` wherever it appears — field rules and reference
rules alike — and selects the codec's deterministic mode for values that rule encrypts. Each rule
MAY declare `namespaces` (prefix → URI) used to evaluate its XPath; a prefix used in `path` but not
declared is a no-match at evaluation time, never an error. The wire format stays flat (§8.1 style:
`method` plus its params at rule level). The rules JSON Schema SHALL be generated from the models,
never hand-written.

#### Scenario: Valid encrypt rule loads
- **WHEN** a rule provides id/channel/operation/path/pii_type with `method: encrypt`
- **THEN** validation succeeds and the action resolves to the encrypt variant with
  `deterministic` defaulting to `false`

#### Scenario: Deterministic encrypt rule loads
- **WHEN** a rule provides `method: encrypt` with `deterministic: true`
- **THEN** validation succeeds and the action carries the deterministic flag

#### Scenario: Deterministic on non-encrypt method rejected
- **WHEN** a rule sets `deterministic: true` with `method: mask` (or `replace`/`remove`)
- **THEN** the entire ruleset is invalid (strict validation, no stray keys)

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
- **THEN** it encodes the method discriminator, per-method required parameters, and the optional
  `deterministic` flag on `encrypt`
