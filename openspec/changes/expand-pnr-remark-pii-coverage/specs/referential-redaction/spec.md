## ADDED Requirements

### Requirement: Redaction never rewrites inside an existing token

Redaction SHALL NOT rewrite any character span that overlaps an `ENC_` token already present in the
node's text, for both extraction (`field` rules with `extract_patterns`) and `reference` matching
within a single response-redaction pass. Token payloads are base64url and therefore contain
`-` and `_`, which reference word-boundary matching treats as boundaries; without this guard a
collected value could match inside a token another rule produced earlier in the pass, and the
partial rewrite would corrupt the ciphertext so the value no longer de-anonymizes. A match that
overlaps an existing token SHALL be left verbatim and SHALL NOT count as a redaction.

#### Scenario: Reference match inside a token is skipped
- **WHEN** a field rule has already encrypted a value into an `ENC_` token whose base64url payload
  happens to contain a collected name bordered by `-`/`_`, and a reference rule then scans that node
- **THEN** the token is left unchanged, the name-inside-token is not rewritten, and the token still
  decrypts to its original plaintext on the way back upstream

#### Scenario: Extraction span inside a token is skipped
- **WHEN** an extraction pattern (e.g. a digit run) would match inside an `ENC_` token another rule
  produced in the same node this pass
- **THEN** that span is left unchanged and only genuine plaintext occurrences are rewritten
