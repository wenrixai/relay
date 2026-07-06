## ADDED Requirements

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
