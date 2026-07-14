# sabre-pii-baseline Specification

## Purpose
Baked baseline PII redaction rules for Sabre response operations: per-operation rule
selection, covered PII fields (element text and attributes), reversible-encrypt vs
one-way-mask action policy, and non-PII preservation guarantees.
## Requirements
### Requirement: Sabre operations covered by the baked ruleset
The baked ruleset (`rules_fallback.json`) SHALL contain field rules for channel `sabre` selected by
body-derived operation, covering the original baseline (`GetReservationRS`, `TravelItineraryReadRS`,
`GetPriceQuoteRS` — plain and PQR variants share one operation name, `AirTicketRS`,
`DailySalesReportRS`) plus the high-priority PII-bearing operations used by Wenrix handlers,
identified by their real SOAP body element name (what `parse_operation` returns), which differs from
the Wenrix service's conceptual API names: `RefundRS` (ticket refund), `DailyRefundReportRS`,
`eTicketCouponRS` (e-ticket details, incl. the exchange-context variant), `GetElectronicDocumentRS`
(ticket info from airline), `GetTicketingDocumentRS`, `TravelItineraryHistoryRS`, and `Trip_SearchRS`
(past-date PNR details). XPaths SHALL be sourced from the Wenrix parsing models
(`sources/itinerary.py`, `ticketing.py`, `pnr.py`, `history.py`, `queue.py`, `sales_report.py`),
which enumerate the elements/attributes carrying names, contact details, documents, and payment data.
Rules SHALL bind every namespace they use explicitly (Sabre payloads use default namespaces — each
rule declares its own prefix→URI map).

Operations whose real responses carry no PII SHALL NOT receive rules and are handled by the coverage
metric (`covered=False`, forwarded unchanged): `QueueAccessRS` (record locators / agent sines / PCC
only), `PassengerDetailsRS` (status-only acknowledgment — passenger data is in the request), and
`AutomatedExchangesRS` (fare/penalty comparison). `CreatePassengerNameRecordRS` has no corpus payload
(the PNR-create operation is `EnhancedAirBookRS`).

#### Scenario: Rules select per operation
- **WHEN** a Sabre response body's SOAP Body first-child local-name is one of the covered operations
- **THEN** only that operation's rules (plus shared-pattern rules whose operation regex matches) apply

#### Scenario: Newly covered operation redacts names
- **WHEN** a `RefundRS`, `eTicketCouponRS`, or `Trip_SearchRS` response carries passenger names
- **THEN** those names are redacted per the rule's action and no plaintext name is forwarded

#### Scenario: Uncovered operation forwarded with coverage metric
- **WHEN** a Sabre response carries an operation with no baseline rules
- **THEN** the relay forwards the body unchanged and emits `pii_uncovered_operation_total{channel,
  operation}` so the gap is discoverable

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
Sanitized fixtures for each covered operation (original and newly added) SHALL live in
`tests/fixtures/sabre/` and drive golden unit tests (rule-level: counts, reversibility, one-way masks,
non-PII preservation) plus relay integration tests (full pipeline: credential swap ordering,
`BinarySecurityToken` encryption via the existing `SabreHandler`, PII redaction). All tests finish
within the configured pytest timeout with no network.

#### Scenario: Golden suite green
- **WHEN** the Sabre golden unit and integration suites run against the baked ruleset
- **THEN** every covered operation redacts per its rules and encrypted fields round-trip

#### Scenario: New-operation fixtures present
- **WHEN** a newly covered operation is added to the baseline
- **THEN** a sanitized fixture for it exists under `tests/fixtures/sabre/` and drives a golden test

### Requirement: Required anchor rules fail closed on schema drift
Each PII-heavy Sabre operation SHALL have exactly one anchor rule (the passenger-name rule) set
`required: true`, so that if Sabre schema drift (element/attribute renames on version bumps) causes
the anchor to locate no nodes or rewrite no values, redaction fails closed (`RedactionError` → 502
`pii_redaction_failed`) rather than forwarding an unredacted response. This SHALL hold for every
covered PII-heavy operation, explicitly including `AirTicketRS`, `DailySalesReportRS`,
`TravelItineraryReadRS`, and `GetPriceQuoteRS`, not only the operations that already carry an anchor.
Where an operation is matched only by rules shared with another operation, it SHALL still have a
`required: true` name anchor scoped so the anchor applies to it.

#### Scenario: Anchor present and drift fails closed
- **WHEN** a covered operation's response no longer contains the anchor rule's target nodes
- **THEN** redaction raises and the relay returns 502 `pii_redaction_failed`, forwarding nothing

#### Scenario: Anchor matches normally
- **WHEN** the anchor rule locates and rewrites the passenger name as expected
- **THEN** redaction proceeds and the response is forwarded with names redacted

#### Scenario: Every PII-heavy operation carries an anchor
- **WHEN** the baked ruleset is inspected for `AirTicketRS`, `DailySalesReportRS`,
  `TravelItineraryReadRS`, and `GetPriceQuoteRS`
- **THEN** each has a passenger-name rule with `required: true` that applies to that operation

