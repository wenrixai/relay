# pii-rules Specification

## Purpose
Define strict PII rule models, actions, validation, loading, and authoring constraints.
## Requirements
### Requirement: Rule schema via pydantic discriminated actions

PII rules SHALL be modeled in pydantic v2 with strict validation (`extra="forbid"`). A ruleset
carries `schema_version`, `rules_version`, and `rules[]`. Each field rule carries `id`, `channel`,
`operation` (compilable regex), `path`, `path_type` (`xpath`, default and only supported value),
`pii_type`, an action, and optional `ignored_content_patterns` (each a compilable regex),
`extract_patterns`, and `required` (default false). Actions SHALL form a discriminated union on
`method`: `encrypt` (`deterministic`, default false), `mask` (`mask_char`, `keep_prefix`), `replace`
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

### Requirement: Local-only rules loading

The relay SHALL load the ruleset exclusively from the baked bundle shipped in the image
(`rules_fallback.json`). There SHALL be no runtime HTTP fetch of rules and no rules-API URL
setting. An incompatible `schema_version` SHALL be rejected wherever it appears. An invalid baked
bundle SHALL abort startup when any channel has PII enabled; without PII enabled it SHALL degrade to
"no rules loaded" (logged, not fatal).

#### Scenario: Baked bundle loads at startup
- **WHEN** the relay starts
- **THEN** the ruleset is parsed from the baked bundle and `rule_version` reports its
  `rules_version`
- **AND** no network request is made to load rules

#### Scenario: Invalid baked bundle aborts with PII enabled
- **WHEN** the baked bundle fails validation and any channel has `pii.enabled: true`
- **THEN** startup aborts with a non-zero exit

#### Scenario: Invalid baked bundle degrades without PII
- **WHEN** the baked bundle fails validation and no channel has PII enabled
- **THEN** the relay starts with no rules loaded, logging the failure

#### Scenario: No polling
- **WHEN** the relay runs after startup
- **THEN** no rules-related requests or re-reads occur

### Requirement: Reference rule kind in the ruleset

The rule schema SHALL support a second rule kind discriminated on `rule_type`: `field` (the implied
default) and `reference`. A `reference` rule SHALL be strict and carry `id`, `channel`, `operation`
(compilable regex), `path`, `path_type` (`xpath`, default and only supported value), optional
`namespaces`, `source_pii_types` (non-empty), `pii_type`, `min_match_len` (integer ≥ 1, default 3),
`word_boundary` (default true), and an `encrypt` action. A `RuleSet.rules[]` SHALL accept a mixed list
of field and reference rules. The generated JSON Schema SHALL encode the rule-kind discriminator.
`pii.force_redact` MAY replace reference encryption with the fixed `"REDACTED"` literal without
changing the stored action.

#### Scenario: Valid reference rule loads
- **WHEN** a rule provides `rule_type: reference`, its selectors, non-empty `source_pii_types`,
  `pii_type`, and `method: encrypt`
- **THEN** validation succeeds and the rule resolves to the reference kind

#### Scenario: Empty source_pii_types rejected
- **WHEN** a reference rule declares an empty `source_pii_types`
- **THEN** validation fails at load time

#### Scenario: Unknown source pii_type rejected
- **WHEN** `source_pii_types` contains a value outside the `pii_type` enumeration
- **THEN** the entire ruleset is invalid (no partial acceptance)

#### Scenario: Mixed ruleset loads
- **WHEN** a ruleset contains valid field and reference XPath rules
- **THEN** each rule is validated against its own kind and the ruleset loads

#### Scenario: Bad regex in reference operation rejected at load
- **WHEN** a reference rule's `operation` is not a compilable regex
- **THEN** validation fails at load time, never at request time

### Requirement: Redaction actions must preserve type validity for typed fields
Rule action choice SHALL preserve the consuming parser's type contract. `encrypt` (which emits an
`ENC_` token) and `mask` with a mask character that is not valid for the field's type are only
correct for free-string fields (names, emails, addresses, remarks). For any field the caller parses
as a non-string type (date, number, enum code), a rule SHALL use `replace` with a fixed schema-valid
value, or `mask` with a mask character that keeps the output type-valid, so redaction never produces
a value that crashes or is rejected by the caller's parser. This is a rules-authoring constraint on
the baked ruleset, verified by contract tests over sanitized fixtures; it does not change engine
behavior.

#### Scenario: Date field uses a schema-valid sentinel
- **WHEN** a rule targets a field the caller parses as a date
- **THEN** the rule uses `replace` (or a numeric/date-preserving `mask`) that yields a parseable date,
  not `encrypt` and not a `*`-masked string

#### Scenario: Enum-code field uses a valid code
- **WHEN** a rule targets a field the caller parses as an enumerated code
- **THEN** the rule uses `replace` with a value inside the field's allowed set (or `remove` if the
  schema marks it optional), never an `ENC_` token or `*` mask

#### Scenario: Free-string field may encrypt or mask freely
- **WHEN** a rule targets a field the caller treats as an opaque string (name, email, remark)
- **THEN** `encrypt` or `mask` with any mask character is permitted

### Requirement: Deterministic encryption control

An encrypt action MAY set `deterministic: true` to request deterministic token encryption. The
default SHALL be false. Deterministic and non-deterministic results SHALL remain isolated even for
the same plaintext, and `deterministic` SHALL be rejected on non-encrypt actions through strict
action validation.

#### Scenario: Deterministic flag loads only for encryption
- **WHEN** an encrypt rule sets `deterministic: true`
- **THEN** the rule loads and requests deterministic encryption

#### Scenario: Deterministic flag on mask rejected
- **WHEN** a mask rule includes `deterministic`
- **THEN** strict validation rejects the ruleset

### Requirement: Extraction patterns select rewritable spans

A field rule MAY declare `extract_patterns`, each containing a compilable regex applied to the
selected node or attribute value. A match with exactly one capture group SHALL rewrite only that
group's span; a match with zero or multiple capture groups SHALL rewrite the full match. Rewrites
SHALL be calculated against the original value, applied without offset corruption, and SHALL NOT
rewrite any byte more than once when patterns overlap. Surrounding non-matched text SHALL remain
unchanged.

#### Scenario: Single capture group preserves surrounding text
- **WHEN** an extraction pattern `BEGINS WITH (\\d{6})` matches a selected value
- **THEN** only the six captured digits are rewritten and the surrounding text is preserved

#### Scenario: Overlapping extraction matches are not double-processed
- **WHEN** two extraction matches overlap in the original selected value
- **THEN** the resulting spans are merged or otherwise applied once without corrupting offsets

### Requirement: Required field rules fail closed

A field rule MAY set `required: true`. After ignored-content and extraction processing, a required
rule SHALL be considered satisfied only when it rewrites at least one value. If it locates no target
or rewrites no value, the complete redaction pass SHALL fail; no partially processed response SHALL
be returned. `required` SHALL apply only to field rules.

#### Scenario: Required target absent fails redaction
- **WHEN** a selected required rule locates no rewritable target for its operation
- **THEN** redaction fails and the response pipeline returns the established fail-closed PII error

#### Scenario: Required target rewritten satisfies rule
- **WHEN** a required rule rewrites at least one value
- **THEN** that rule does not prevent the remaining redaction pass from completing
