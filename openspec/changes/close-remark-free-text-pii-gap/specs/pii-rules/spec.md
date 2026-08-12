## ADDED Requirements

### Requirement: Traveller-adjacent third parties are data subjects; agency staff are operational

The baked ruleset SHALL treat a natural person recorded in a booking *because of their relationship to
the traveller* as a data subject, redacted on the same terms as the passenger. This covers at least
emergency contacts, authority-to-charge / payment-authorising persons, travel arrangers and bookers,
and the Amadeus orderer.

Personal names and identifiers belonging to **agency staff acting in their professional capacity** —
full agent names in audit remarks, agent sign-in codes, duty codes, pseudo-city codes — SHALL NOT be
redacted. Redacting them would destroy the audit legibility the remark trail exists to provide, and
extends the existing "agent sign-in codes are not PII" classification consistently to the name form.

#### Scenario: Emergency contact is redacted
- **WHEN** a response carries an emergency-contact name or phone number in free text with no
  structured counterpart anywhere in the document
- **THEN** the value is redacted and the operational marker around it (for example `EMER-`) is
  preserved

#### Scenario: Travel arranger is redacted across every rendering
- **WHEN** the same travel-arranger name appears in a contact phone node, a remark line, an invoice
  remark field, and a ticketing comment
- **THEN** every occurrence is redacted, and occurrences reached by the reference pass carry the same
  token as the occurrence the field rule collected

#### Scenario: Agent name and sine are preserved
- **WHEN** a remark records the acting agent, either by full name (for example
  `ADVISED BY - <agent name>`) or by short sign-in code (for example `12AUG2026-<sine>-…`)
- **THEN** the value is preserved verbatim in the anonymized response

### Requirement: Person-linked pseudonymous identifiers are PII; organisation codes are not

An identifier that resolves to one natural person SHALL be treated as PII and encrypted (reversible,
because clients legitimately correlate travellers across bookings by these keys). This covers at least
employer employee ids, traveller profile ids in every namespace that mirrors them, and
loyalty/contract numbers attached to an individual traveller.

An identifier that resolves only to an organisation — corporate account ids, corporate contract and
deal codes, tour codes, negotiated-fare discount codes — SHALL NOT be redacted; it is commercial data,
and removing it breaks fare reissue and corporate policy display.

#### Scenario: Employee id is encrypted wherever it appears
- **WHEN** an employee id appears both as a structured attribute and inside remark free text
- **THEN** both occurrences are replaced by the same reversible token

#### Scenario: Traveller profile id is encrypted in every mirror namespace
- **WHEN** a traveller profile id is emitted in more than one namespace for the same reservation
- **THEN** every occurrence is encrypted, while agency-level and corporate-level profile ids for the
  same reservation are preserved

#### Scenario: Corporate account code is preserved
- **WHEN** a response carries an organisation-level corporate account, contract, tour or discount code
- **THEN** the value is preserved verbatim

### Requirement: Free-text identity-document spans use format-preserving sentinels

A rule redacting identity-document data embedded in free text SHALL replace the span with a sentinel
that preserves the original shape in the format used at that location, rather than a `REDACTED`
literal. This applies to date of birth, gender, document number, document dates and nationality, and
extends the existing typed-field sentinel policy to free text so that consumer-side text parsing of
the surrounding operational line keeps working.

#### Scenario: Date of birth in a remark keeps its date shape
- **WHEN** a remark line carries a date of birth in a `DDMMMYY` free-text span
- **THEN** the span is replaced with a `DDMMMYY`-shaped sentinel, and the surrounding marker text is
  preserved

#### Scenario: Passport number in a remark keeps its length class
- **WHEN** a remark line carries a passport number in a free-text span
- **THEN** the span is replaced with a document-number-shaped sentinel, not a `REDACTED` literal
