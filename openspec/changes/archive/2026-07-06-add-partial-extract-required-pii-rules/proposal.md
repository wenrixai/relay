# Proposal: Partial Extract and Required PII Rules

## Motivation
Some channel fields contain PII embedded inside a larger structured value, such as an email address
inside a Sabre `Data` node. Existing `field` rules replace the whole selected text or attribute,
which can remove surrounding non-PII context. Some mappings are also mandatory for privacy coverage:
if a required selector or extraction no longer matches, the relay must fail closed instead of
silently returning unredacted PII.

## Approach
- Extend `field` rules with optional `extract_patterns`, allowing regex extraction inside a selected
  XML text or attribute value while preserving the surrounding text.
- Extend `field` rules with `required: false` by default. Required rules fail response redaction when
  no selected value is rewritten.
- Keep the existing public rule names: `method` is the action and `operation` is the channel
  operation matcher. Do not add aliases for `channel_operation` or `ignore_if_missing`.

## Non-goals
- Raw-body regex replacement.
- Request-path rule evaluation; de-anonymization remains token driven.
- JSONPath execution.
