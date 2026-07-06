# redaction-engine Specification Delta

## MODIFIED Requirements

### Requirement: Response redaction
For `field` rules without `extract_patterns`, response redaction SHALL preserve the existing
whole-value behavior. For `field` rules with `extract_patterns`, the relay SHALL apply the rule's
action only to each extracted span inside the selected XML text or attribute value, preserving all
surrounding text. `encrypt` SHALL produce one `ENC_` token per extracted span; `mask`, `replace`,
and `remove` SHALL apply only to the extracted span. Extracted plaintext spans SHALL be collected
before rewriting for same-pass `reference` rules.

If a `field` rule has `required: true`, redaction SHALL fail closed with `pii_redaction_failed`
when the rule selects no XPath results, when all selected values are ignored or empty, or when
`extract_patterns` are present but produce zero extracted spans. No partially processed response
body SHALL be forwarded.

#### Scenario: Partial email masking
- **WHEN** a selected text value contains surrounding text and an email matched by `extract_patterns`
- **THEN** only the email span is masked and the surrounding text is preserved

#### Scenario: Partial extraction encrypts and round trips
- **WHEN** an extracted span uses `method: encrypt`
- **THEN** the span is replaced by an `ENC_` token that decrypts to the extracted plaintext

#### Scenario: Required rule missing path fails closed
- **WHEN** a required rule selects no XPath results
- **THEN** response redaction fails and no partial response is forwarded

#### Scenario: Required extract no-match fails closed
- **WHEN** a required rule selects values but none match its `extract_patterns`
- **THEN** response redaction fails and no partial response is forwarded
