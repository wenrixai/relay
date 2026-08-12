## ADDED Requirements

### Requirement: Amadeus form-of-payment and other-service free text are covered

The Amadeus baseline SHALL cover the `FP` (form of payment) and `OS` (other service information)
`dataElementsIndiv` free-text nodes, not only the `AP` and `RM` elements it targeted previously. All
four use the same `otherDataFreetext/longFreetext` carrier; `FP` holds a card number and expiry, and
`OS` holds traveller-attached contract numbers.

#### Scenario: Card number in the FP element is redacted
- **WHEN** a `PNR_Reply` carries a form-of-payment line such as `PAX CC<type><masked pan>/<mmyy>`
- **THEN** the card number and the expiry are redacted and the operational prefix is preserved —
  supplier-side masking is not trusted

#### Scenario: Traveller contract number in the OS element is encrypted
- **WHEN** an `OS` line carries a traveller-attached contract or loyalty number (for example
  `CP/<carrier><digits>`)
- **THEN** the number is encrypted, while organisation-level corporate account codes in sibling `OS`
  lines (for example `CMP …`, `OIN …`, `NCA …`) are preserved

### Requirement: Amadeus RM remark rules cover both remark mirrors

Amadeus remark extraction patterns SHALL NOT require a leading `*`, so that both renderings of every
remark match. Each Amadeus RM/RIR element is emitted twice for the same remark: once under
`miscellaneousRemarks/remarks/freetext` with the leading `*` inside the text, and once under
`extendedRemark/structuredRemark/freetext` with that `*` hoisted into the sibling `category` element.

#### Scenario: Orderer name is redacted in both mirrors
- **WHEN** a `PNR_Reply` carries an orderer name as `*ACEORB-<name>` and `*ACECRM-ORDERER-<name>`, each
  duplicated into the `structuredRemark` mirror without the leading `*`
- **THEN** every occurrence is encrypted and the `ACEORB-` / `ACECRM-ORDERER-` markers are preserved

#### Scenario: Date of birth and gender in a remark are redacted
- **WHEN** a remark carries `DOB-<ddmmmyy>/GENDER-<mf>` in both mirrors
- **THEN** both spans are replaced with format-preserving sentinels in both mirrors

#### Scenario: Person-linked identifiers in remarks are encrypted
- **WHEN** remarks carry an employee id (`ACECRM-EMPLOYEE ID-<digits>`), a booking-tool traveller
  profile reference (`CYTRIC PROFILE REF:<digits>`), or a traveller hotel-loyalty preference id
  (`PREF HTL ID/SUP-<cc>/ID-<digits>`)
- **THEN** each identifier is encrypted while its marker text and any template remark that carries the
  marker with no value are preserved
