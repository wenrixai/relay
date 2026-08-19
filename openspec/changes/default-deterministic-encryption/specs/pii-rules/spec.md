## MODIFIED Requirements

### Requirement: Rule schema via pydantic discriminated actions

PII rules SHALL be modeled in pydantic v2 with strict validation (`extra="forbid"`). A ruleset
carries `schema_version`, `rules_version`, and `rules[]`. Each field rule carries `id`, `channel`,
`operation` (compilable regex), `path`, `path_type` (`xpath`, default and only supported value),
`pii_type`, an action, and optional `ignored_content_patterns` (each a compilable regex),
`extract_patterns`, and `required` (default false). Actions SHALL form a discriminated union on
`method`: `encrypt` (`deterministic`, default true), `mask` (`mask_char`, `keep_prefix`), `replace`
(`replacement` required), `remove` (no params). Each rule MAY declare `namespaces` (prefix → URI)
used to evaluate its XPath. The wire format stays flat (`method` plus its params at rule level).
The rules JSON Schema SHALL be generated from the models, never hand-written. A channel's
`pii.force_redact` config MAY override the effective outcome of an `encrypt` action at apply time
without changing the stored rule.

#### Scenario: Valid encrypt rule loads
- **WHEN** a rule provides id/channel/operation/path/pii_type with `method: encrypt`
- **THEN** validation succeeds and the action resolves to the encrypt variant

#### Scenario: Unsupported path type rejects ruleset
- **WHEN** any field or reference rule sets `path_type` to `jsonpath` or another unsupported value
- **THEN** the entire ruleset is invalid at load time and no rule is silently skipped

#### Scenario: Replace without replacement rejected
- **WHEN** a rule sets `method: replace` without `replacement`
- **THEN** validation fails naming the missing parameter

#### Scenario: Unknown method rejects ruleset
- **WHEN** any rule carries an unrecognized `method`
- **THEN** the entire ruleset is invalid (fail closed; no partial acceptance)

#### Scenario: Bad regex rejected at load
- **WHEN** `operation`, an `ignored_content_patterns` entry, or an extraction pattern is not a
  compilable regex
- **THEN** validation fails at load time (never at request time)

#### Scenario: Generated schema documents actions
- **WHEN** the JSON Schema is generated from the rule models
- **THEN** it encodes the method discriminator, per-method parameters, XPath-only path type,
  extraction patterns, and required-rule flag

#### Scenario: Generated schema records the deterministic default
- **WHEN** the JSON Schema is generated from the rule models
- **THEN** the encrypt action's `deterministic` property carries `default: true`

### Requirement: Deterministic encryption control

An encrypt action SHALL carry a `deterministic` flag whose default is **true**: an encrypt rule that
does not mention the flag SHALL request deterministic token encryption. An encrypt action SHALL
support `deterministic: false` to opt that rule back to random-IV encryption. Deterministic and
non-deterministic results SHALL remain isolated even for the same plaintext, and `deterministic`
SHALL be rejected on non-encrypt actions through strict action validation.

Because the default is deterministic, every encrypt rule in a ruleset SHALL be assumed to produce
equality-comparable tokens unless it opts out. Rule authors SHALL set `deterministic: false` on
fields where cross-response correlation of the redacted value is unacceptable.

#### Scenario: Encrypt rule omitting the flag is deterministic
- **WHEN** an encrypt rule carries no `deterministic` key
- **THEN** the rule loads with `deterministic` true and requests deterministic encryption

#### Scenario: Deterministic flag loads only for encryption
- **WHEN** an encrypt rule sets `deterministic: true`
- **THEN** the rule loads and requests deterministic encryption

#### Scenario: Opt-out loads as random-IV
- **WHEN** an encrypt rule sets `deterministic: false`
- **THEN** the rule loads and requests random-IV encryption

#### Scenario: Deterministic flag on mask rejected
- **WHEN** a mask rule includes `deterministic`
- **THEN** strict validation rejects the ruleset
