## MODIFIED Requirements

### Requirement: Contact, identity-document, and loyalty redaction
For `GetReservationRS` the baseline SHALL redact: email addresses
(`stl19:EmailAddress/stl19:Address`, encrypt), phone numbers
(`stl19:PhoneNumber/stl19:Number`, mask), postal address lines
(`stl19:AddressLine/stl19:Text`, mask), APIS DOCS entries (`stl19:DOCSEntry` children:
`Surname`, `Forename`, `MiddleName` — mask, pii type `person`; `DateOfBirth` — `replace` with the
fixed schema-valid sentinel date `1901-01-01`, pii type `dob`; `Gender` — `replace` with the fixed
valid code `M`, pii type `gender`), DOCO free text (`stl19:DOCOEntry/stl19:FreeText`, mask, pii type
`visa`), and frequent-flyer numbers (`stl19:FrequentFlyer/stl19:Number`, encrypt). `DateOfBirth` and
`Gender` are typed fields the caller parses (ISO date / enum code), so their redacted output SHALL
remain schema-valid rather than a `*`-masked string that breaks parsing.

#### Scenario: DOB replaced with a valid sentinel date
- **WHEN** a `DOCSEntry` carries `DateOfBirth` `1994-07-01`
- **THEN** the value is replaced with `1901-01-01` (no `ENC_` token; not reversible) and parses as an
  ISO date

#### Scenario: Gender replaced with a valid code
- **WHEN** a `DOCSEntry` carries `Gender` `F`
- **THEN** the value is replaced with `M` (no `ENC_` token; not reversible), a schema-valid gender code

#### Scenario: Name fields masked one-way
- **WHEN** a `DOCSEntry` carries `Surname`/`Forename`
- **THEN** each value is masked (no `ENC_` token; not reversible)

#### Scenario: Frequent flyer round-trips
- **WHEN** `FrequentFlyer/Number` is encrypted and later sent back in a request
- **THEN** de-anonymization restores the original number

### Requirement: Payment redaction
Card data SHALL be redacted as pii type `payment` even when the supplier pre-masks it:
`or114:PaymentCard/or114:CardNumber` text (live and inside `stl19:History`), pqs
`PaymentInfo/Card/@number`, and the OB-fee BIN (`OBFee/BankIdentificationNumber` text plus the
BIN echoed in `OBFee/Description` free text via an extract pattern). Card expiry
(`or114:ExpiryMonth`, `or114:ExpiryYear`) SHALL be masked with the numeric mask character `0` so the
masked value stays a schema-valid number (`12` → `00`, `2027` → `0000`), never `*` which the caller's
expiry parser rejects.

#### Scenario: Pre-masked card number still redacted
- **WHEN** a response carries `CardNumber` `4XXXXXXXXXXX4848`
- **THEN** the value is rewritten (mask) — supplier masking is not trusted as sufficient

#### Scenario: Card expiry masked to digits
- **WHEN** a `PaymentCard` carries `ExpiryMonth` `12` and `ExpiryYear` `2027`
- **THEN** each becomes an all-`0` numeric string of the same length (`00`, `0000`), never containing
  `*`

#### Scenario: BIN inside description extracted
- **WHEN** `OBFee/Description` reads `CC NBR BEGINS WITH 460901`
- **THEN** only the 6-digit BIN span is rewritten and the surrounding text is preserved
