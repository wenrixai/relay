## ADDED Requirements

### Requirement: PNR-retrieve baseline scrubs free-text, history, and contact PII

The baked baseline ruleset for the PNR-retrieve operations SHALL redact passenger PII wherever it
appears in the response, not only in the primary structured name/email/phone fields. For Amadeus
`PNR_Reply` and Sabre `GetReservationRS` this SHALL include names, emails, and phone numbers carried
in remark free text, booking history, payment/accounting blocks, and contact sub-structures. This is
a rules-authoring constraint on the baked ruleset, verified by contract tests over sanitized
fixtures; it does not change engine behavior.

#### Scenario: Amadeus remark-only PII is scrubbed
- **WHEN** a `PNR_Reply` carries a passenger name, phone, or emergency-contact name only inside an
  RM remark free-text node (`NAME-…`, `*ARR*…`, `ECTC/…/N-…`), with no matching structured field
- **THEN** each such value is redacted and the surrounding operational remark text is preserved

#### Scenario: Amadeus given-name honorific preserved
- **WHEN** a `PNR_Reply` given-name field holds a name followed by an honorific (e.g. `JANGBIN MR`)
- **THEN** only the name is tokenized and the honorific remains, and the bare name is available to
  the reference pass so it is also scrubbed from remark free text

#### Scenario: Sabre history, payment, and contact PII is scrubbed
- **WHEN** a `GetReservationRS` carries names in the payment `PassengerName`, history `Passengers/Name`
  / `Content` / `HistoryAssociationElement`, `AccountingLineText`, or `or114:Comment`; a contact email
  in `PassengerContactEmail`; or a `¤`/`//`-obfuscated email in a remark or history node
- **THEN** each such value is redacted while non-PII operational text around it is preserved

#### Scenario: Sabre phone nodes with trailing suffixes are masked whole
- **WHEN** a `GetReservationRS` history phone node holds a value with a trailing suffix
  (e.g. `MSP1-6125550100-W`)
- **THEN** the whole node is masked as a unit, so the number is gone and no `ENC_` token abuts the
  suffix

#### Scenario: Glued-code name is a documented limitation
- **WHEN** a name is embedded in an alphanumeric agency code with no word boundary
  (e.g. `*13-JLASTFIRST`)
- **THEN** it is not scrubbed — word-boundary matching is retained to avoid over-redaction — and this
  is an accepted limitation, not a regression
