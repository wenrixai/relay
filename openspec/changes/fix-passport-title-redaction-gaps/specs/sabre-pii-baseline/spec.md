## ADDED Requirements

### Requirement: Travel-document number, expiry, and nationality redaction
For `GetReservationRS` the baseline SHALL redact every travel-document identifier carried by the APIS
block, in both the `stl19` structured entry and the `or114` history mirror:

- `DocumentNumber` — mask, pii type `passport_id` — wherever it appears
  (`stl19:DOCSEntry`, `or114:TravelDocument`, `or114:OtherSupplementaryInformation`).
- `DocumentExpirationDate` — `replace`, pii type `passport_id` — with a schema-valid sentinel date.
- `CountryOfIssue` / `DocumentIssueCountry` / `DocumentNationalityCountry` — `replace`, pii type
  `nationality` — with a schema-valid two-letter country code.

The document kind (`stl19:DocumentType`, `or114:Type`) is an enum describing the document, not an
identifier of the passenger, and SHALL be preserved.

#### Scenario: Passport number masked in every location
- **WHEN** a `GetReservationRS` carries the same passport number in `stl19:DOCSEntry/DocumentNumber`,
  `or114:TravelDocument/DocumentNumber`, and `or114:OtherSupplementaryInformation/DocumentNumber`
- **THEN** every occurrence is masked (no `ENC_` token; not reversible) and the plaintext number does
  not survive anywhere in the response

#### Scenario: Expiry date replaced with a valid sentinel
- **WHEN** a travel document carries `DocumentExpirationDate`
- **THEN** the value is replaced with a sentinel date that parses in the same format the node used, so
  a caller reading the field as a date is not broken

#### Scenario: Nationality replaced with a valid country code
- **WHEN** a travel document carries `CountryOfIssue`, `DocumentIssueCountry`, or
  `DocumentNationalityCountry`
- **THEN** each value is replaced with a schema-valid two-letter code and the real country does not
  survive

#### Scenario: Document kind preserved
- **WHEN** a `DOCSEntry` carries `DocumentType` `PP`
- **THEN** the value survives verbatim

### Requirement: Typed date sentinels match the format of the node they replace
Where the same logical field appears in two namespaces with different date formats, the baseline SHALL
emit a sentinel in the format that node natively uses. `stl19` document dates are ISO
(`YYYY-MM-DD`); the `or114` history mirror uses `DDMMMYYYY`. A sentinel in the wrong format is a
defect even though the real value is gone, because the caller parses the field by node, and because an
out-of-format sentinel reads to a reviewer as unredacted live data.

#### Scenario: History-mirror date of birth keeps its native format
- **WHEN** `or114:TravelDocument/DateOfBirth` carries `01JAN1990`
- **THEN** the value is replaced with `01JAN1900`, not with an ISO date

#### Scenario: Structured date of birth stays ISO
- **WHEN** `stl19:DOCSEntry/DateOfBirth` carries `1990-01-01`
- **THEN** the value is replaced with `1900-01-01`
