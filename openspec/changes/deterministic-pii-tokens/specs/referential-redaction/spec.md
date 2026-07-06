## ADDED Requirements

### Requirement: Reference hits reuse collected-value tokens
A reference-rule hit SHALL reuse the token already minted during the same pass for the identical
exact plaintext under the same encryption mode (the phase-1 field-rule token, or an earlier
reference hit's token), instead of re-encrypting with a fresh IV. When no token exists yet for that
exact plaintext and mode, the reference rule SHALL encrypt per its own action and the result SHALL
join the pass-scoped cache. Because reference matching is case-insensitive while encryption
preserves the matched casing, a case-variant occurrence SHALL be encrypted as its own exact
plaintext (round-trip casing fidelity outranks cross-casing token equality).

#### Scenario: Remark occurrence shares the field token
- **WHEN** a field rule encrypts `//Passenger/Last` holding "SMITH" and a reference rule then hits
  "SMITH" inside a remark in the same response
- **THEN** the remark span is replaced with the same `ENC_` token the field received

#### Scenario: Repeated remark hits share one token
- **WHEN** the same collected value occurs twice inside reference-rule target text
- **THEN** both spans receive the identical token and the redaction count increases by two

#### Scenario: Case variant gets its own token
- **WHEN** "Smith" was collected and tokenized, and a remark contains "SMITH"
- **THEN** "SMITH" is matched (case-insensitive) but encrypted as "SMITH", yielding a token that
  decrypts to "SMITH", distinct from the "Smith" token
