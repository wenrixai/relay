# pii-rules Specification (delta)

## ADDED Requirements

### Requirement: Rule schema via pydantic discriminated actions
PII rules SHALL be modeled in pydantic v2 with strict validation (`extra="forbid"`). A ruleset
carries `schema_version`, `rules_version`, and `rules[]`. Each field rule carries `id`, `channel`,
`operation` (compilable regex), `path`, `path_type` (`xpath` default | `jsonpath`), `pii_type`, an
action, and optional `ignored_content_patterns` (each a compilable regex). Actions SHALL form a
discriminated union on `method`: `encrypt` (no params), `mask` (`mask_char`, `keep_prefix`),
`replace` (`replacement` required), `remove` (no params). The wire format stays flat (§8.1 style:
`method` plus its params at rule level). The rules JSON Schema SHALL be generated from the models,
never hand-written.

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

### Requirement: Startup fetch with baked fallback
The relay SHALL fetch the ruleset from `RELAY_RULES_API_URL` once at startup (single attempt, short
timeout, no retries, no periodic polling). On any fetch or validation failure it SHALL fall back to
the baked bundle shipped in the image, logging the failure and recording the loaded version in the
`rule_version` gauge. An incompatible `schema_version` SHALL be rejected wherever it appears; an
invalid baked bundle SHALL abort startup when any channel has PII enabled.

#### Scenario: Successful fetch wins
- **WHEN** the rules API returns a valid ruleset at startup
- **THEN** the fetched ruleset is active and `rule_version` reports its `rules_version`

#### Scenario: Fetch failure falls back
- **WHEN** the rules API times out or returns malformed/incompatible content
- **THEN** the baked bundle is active and the failure is logged (no retry, no crash)

#### Scenario: No polling
- **WHEN** the relay runs after startup
- **THEN** no further rules-API requests are made
