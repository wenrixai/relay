# sabre-pii-baseline Specification

## Purpose
Baked baseline PII redaction rules for Sabre response operations: per-operation rule
selection, covered PII fields (element text and attributes), reversible-encrypt vs
one-way-mask action policy, and non-PII preservation guarantees.
## Requirements
### Requirement: Sabre operations covered by the baked ruleset
The baked ruleset (`rules_fallback.json`) SHALL contain field rules for channel `sabre` selected by
body-derived operation, covering at least: `GetReservationRS`, `TravelItineraryReadRS`,
`GetPriceQuoteRS` (plain and PQR variants share one operation name), `AirTicketRS`, and
`DailySalesReportRS`. Rules SHALL bind every namespace they use explicitly (Sabre payloads use
default namespaces — e.g. `http://webservices.sabre.com/pnrbuilder/v1_19`,
`http://www.sabre.com/ns/Ticketing/pqs/1.0`, `http://services.sabre.com/res/tir/v3_10`,
`http://webservices.sabre.com/sabreXML/2011/10`, `http://services.sabre.com/sp/air/ticket/v1`,
`http://services.sabre.com/res/or/v1_14` — each rule declares its own prefix→URI map).

#### Scenario: Rules select per operation
- **WHEN** a Sabre response body's SOAP Body first-child local-name is one of the covered operations
- **THEN** only that operation's rules (plus shared-pattern rules whose operation regex matches) apply

#### Scenario: Uncovered operation applies no rules
- **WHEN** a Sabre response carries an operation with no baseline rules
- **THEN** redaction rewrites nothing and the body is returned unchanged

### Requirement: Name redaction in both element text and attributes
Passenger names SHALL be redacted reversibly (`encrypt`) wherever they appear: element text
(`stl19:Passenger/stl19:LastName|FirstName`, `or114:NameAssociation/or114:LastName|FirstName`,
`AirTicketRS Summary/FirstName|LastName`, `DailySalesReportRS IssuanceData/PersonName`,
`tir310:PassengerData`, `stl19:TicketDetails/stl19:PassengerName`) and attributes
(pqs `NameAssociation/@firstName|@lastName`, `NameAssociationInfo/@firstName|@lastName`,
`ExchangeDocInfo/PassengerName/@firstName|@lastName`) — including the pqs `PriceQuoteInfo`
structure embedded inside `GetReservationRS`.

#### Scenario: Attribute names encrypted
- **WHEN** a `GetPriceQuoteRS` carries `NameAssociation/@firstName="JANE" @lastName="DOE"`
- **THEN** both attribute values become `ENC_` tokens that decrypt back to the originals

#### Scenario: Embedded price-quote names covered in GetReservationRS
- **WHEN** a `GetReservationRS` embeds a pqs `PriceQuoteInfo` with name attributes
- **THEN** those attributes are encrypted by the same shared rule that covers `GetPriceQuoteRS`

#### Scenario: Slash-format PersonName encrypted
- **WHEN** a `DailySalesReportRS` `IssuanceData/PersonName` holds `SURNAME/GIVEN TITLE` text
- **THEN** the full value is replaced with one `ENC_` token

### Requirement: Contact, identity-document, and loyalty redaction
For `GetReservationRS` the baseline SHALL redact: email addresses
(`stl19:EmailAddress/stl19:Address`, encrypt), phone numbers
(`stl19:PhoneNumber/stl19:Number`, mask), postal address lines
(`stl19:AddressLine/stl19:Text`, mask), APIS DOCS entries (`stl19:DOCSEntry` children
`DateOfBirth`, `Gender`, `Surname`, `Forename`, `MiddleName` — mask; pii types `dob`/`gender`/
`person`), DOCO free text (`stl19:DOCOEntry/stl19:FreeText`, mask, pii type `visa`), and
frequent-flyer numbers (`stl19:FrequentFlyer/stl19:Number`, encrypt).

#### Scenario: DOCS entry masked one-way
- **WHEN** a `DOCSEntry` carries `DateOfBirth` `1994-07-01` and `Surname`/`Forename`
- **THEN** each value is masked (no `ENC_` token; not reversible)

#### Scenario: Frequent flyer round-trips
- **WHEN** `FrequentFlyer/Number` is encrypted and later sent back in a request
- **THEN** de-anonymization restores the original number

### Requirement: Payment redaction
Card data SHALL be redacted as pii type `payment` even when the supplier pre-masks it:
`or114:PaymentCard/or114:CardNumber` text (live and inside `stl19:History`), pqs
`PaymentInfo/Card/@number`, and the OB-fee BIN (`OBFee/BankIdentificationNumber` text plus the
BIN echoed in `OBFee/Description` free text via an extract pattern). Card expiry
(`or114:ExpiryMonth`, `or114:ExpiryYear`) SHALL be masked.

#### Scenario: Pre-masked card number still redacted
- **WHEN** a response carries `CardNumber` `4XXXXXXXXXXX4848`
- **THEN** the value is rewritten (mask) — supplier masking is not trusted as sufficient

#### Scenario: BIN inside description extracted
- **WHEN** `OBFee/Description` reads `CC NBR BEGINS WITH 460901`
- **THEN** only the 6-digit BIN span is rewritten and the surrounding text is preserved

### Requirement: Free-text and referential coverage
Remark and SSR free-text nodes SHALL be covered by `reference` rules
(`stl19:RemarkLine/stl19:Text`, `stl19:GenericSpecialRequests/stl19:FreeText|FullText`,
`or114:ServiceRequest/or114:FreeText|FullText`) that encrypt occurrences of values already collected by the
structured name/email/phone/frequent-flyer field rules, so PII echoed into free text does not
survive redaction while non-PII operational text is preserved.

#### Scenario: Name echoed in remark encrypted
- **WHEN** a remark line contains a passenger surname collected by a name rule in the same pass
- **THEN** that occurrence is replaced with an `ENC_` token and the rest of the line is unchanged

#### Scenario: Operational remark untouched
- **WHEN** a remark contains no collected PII values
- **THEN** the remark text is unchanged

### Requirement: Non-PII preservation
Baseline rules SHALL NOT rewrite operational data: PNR record locators, `UpdateToken`, ticket /
EMD / invoice document numbers, monetary amounts and currency codes, agent sines, pseudo-city
codes, DK numbers, seat numbers, itinerary segments, and ebXML `MessageHeader` routing identifiers.

#### Scenario: Locator and ticket number preserved
- **WHEN** a `GetReservationRS` is redacted
- **THEN** `RecordLocator` and `TicketNumber` values are byte-identical to the input

### Requirement: Golden coverage from sanitized fixtures
Sanitized fixtures for each covered operation SHALL live in `tests/fixtures/sabre/` and drive
golden unit tests (rule-level: counts, reversibility, one-way masks, non-PII preservation) plus
relay integration tests (full pipeline: credential swap ordering, `BinarySecurityToken`
encryption via the existing `SabreHandler`, PII redaction). All tests finish within the configured
pytest timeout with no network.

#### Scenario: Golden suite green
- **WHEN** the Sabre golden unit and integration suites run against the baked ruleset
- **THEN** every covered operation redacts per the scenarios above and encrypted fields round-trip
