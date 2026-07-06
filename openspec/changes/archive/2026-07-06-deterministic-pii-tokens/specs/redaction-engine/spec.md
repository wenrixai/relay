## ADDED Requirements

### Requirement: Intra-pass token reuse
Within a single response-redaction pass the relay SHALL maintain a plaintext→token cache so that
encrypting the same exact plaintext under the same encryption mode yields the same `ENC_` token
everywhere it occurs in that response — across repeated field-rule matches and reference-rule hits
alike. The cache SHALL be keyed on the exact plaintext plus the action's deterministic flag (tokens
are never shared between deterministic and non-deterministic rules), SHALL live only for the
duration of the single redaction pass, and SHALL NOT be persisted, logged, or shared across
requests or documents. Redaction counts SHALL count every rewritten occurrence, including
cache-served ones.

#### Scenario: Repeated field value shares one token
- **WHEN** two nodes matched by encrypt field rules in one response hold the identical plaintext
- **THEN** both are rewritten to the same `ENC_` token, and it decrypts to that plaintext

#### Scenario: Distinct values get distinct tokens
- **WHEN** two nodes hold different plaintexts
- **THEN** their tokens differ

#### Scenario: No cross-response reuse in default mode
- **WHEN** the same plaintext appears in two separate responses redacted by non-deterministic
  encrypt rules
- **THEN** the two responses carry different tokens (the cache does not outlive a pass)

#### Scenario: Mode isolation
- **WHEN** a deterministic encrypt rule and a non-deterministic encrypt rule both match the same
  plaintext in one response
- **THEN** the deterministic rule's nodes and the non-deterministic rule's nodes carry different
  tokens, each valid for decryption
