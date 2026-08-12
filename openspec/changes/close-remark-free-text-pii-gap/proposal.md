## Why

A customer reported PII surviving anonymization, "mainly in remarks". Two real captured responses
(Amadeus `PNR_Reply`, Sabre `GetReservationRS`) were replayed through the shipped baked ruleset with
the real engine. The passenger's own identity redacts correctly — structured name, phone, email,
DOCS/APIS entries, frequent-flyer number and card all scrubbed. Two specific classes still leak:

- **PII that exists only in free text.** The phase-2 reference pass can only scrub values that a
  phase-1 field rule already collected, so any value with no structured counterpart is invisible to
  it. This is exactly the third-party population: emergency contact (`EMER-<name>`, `EMER-<phone>`),
  authority-to-charge (`TPREF-AUTH-AUTHORITY TO CHARGE-<name>`), travel arranger (`TRAVEL ARRANGER/…`,
  `*84-…`, the `CTC` phone node, `ReceivedFrom/Name`, `FutureTicketing/Comment`) and the Amadeus
  orderer (`ACEORB-…`, `ACECRM-ORDERER-…`). The observed proof is a single node reading
  `EMER-YAARA <ENC_…>`: the passenger surname beside it *was* scrubbed by the reference rule, while
  the emergency contact's given name survived because nothing had collected it.
- **Sabre history mirrors for one-way types.** Every coded passenger remark is re-emitted three times
  — `RemarkLine/Text`, `HistoryAssociationElement`, and `AssociationChild`/`AssociationParent/Content`
  (with the remark code turned into a `P!`/`V!`/`E!` prefix). `ReferenceRule` accepts only
  `EncryptAction`, so date-of-birth, passport number, nationality and card data — whose policy is
  one-way replacement — cannot be propagated to those mirrors by the reference pass at all. Confirmed
  leaks: `BIRTHDATE-07AUG70`, `PSPT-IL <passport> …`, `PSPT/CO-IL/NR-<passport>/IS-…/EX-…/CI-IL`,
  `CTZN-IL`, and a masked PAN `*CA5XXXXXXXXXXX8630/1127` appearing 20 times.

Two further gaps are structural rather than free-text: no rule covers the Amadeus `FP` (form of
payment) or `OS` (other service information) `dataElementsIndiv` at all, so a card number sits in
cleartext in `PAX CCDCXXXXXXXXXX7298/0629`; and person-linked pseudonymous identifiers (employee id,
traveller profile id, traveller-attached loyalty/contract numbers) are unclassified today and survive
in both channels.

## What Changes

- **Scope decision: traveller-adjacent third parties are data subjects.** Emergency contacts,
  authority-to-charge holders, travel arrangers and the Amadeus orderer SHALL be redacted like the
  passenger. **Agency-agent personal names and sign-in codes remain operational** and SHALL be
  preserved — this keeps the existing "agent sign-in codes are not PII" stance and keeps remark
  audit trails legible for the customer.
- **Scope decision: person-linked pseudonymous identifiers are PII.** Employee ids, traveller profile
  ids, and loyalty/contract numbers attached to a traveller SHALL be encrypted (reversible — clients
  legitimately correlate them). Organisation-wide commercial codes (corporate account ids such as
  `OIN CHEVRON`/`CMP …`, tour codes, discount codes) are NOT personal data and SHALL be preserved,
  since redacting them breaks fare reissue and policy display.
- **Identity-document data found in free text gets format-preserving sentinels** (`01JAN00`,
  `00000000`, `31DEC99`, `ZZ`, `M`) rather than `REDACTED`, extending the existing typed-field
  sentinel policy from structured nodes to free-text spans so downstream text parsers keep working.
- **Rules only reach values via literal markers.** Every new `extract_patterns` entry anchors on an
  operational marker observed in a payload (`EMER-`, `BIRTHDATE-`, `PSPT-`, `PSPT/CO-`, `CTZN-`,
  `AUTHORITY TO CHARGE-`, `TRAVEL ARRANGER/`, `ACEORB-`, `ACECRM-EMPLOYEE ID-`, `CYTRIC PROFILE REF:`,
  `PREF HTL ID/`, `DHSNBR-PAX-`, `ISS TKT FR`). No generic shape matching over free text: an
  unanchored date or digit-run pattern would redact fares, flight dates and city pairs.
- **One-way types name their mirrors explicitly.** Rules for date-of-birth, gender, passport,
  nationality and card fragments in Sabre remarks SHALL also target `HistoryAssociationElement` and
  `AssociationChild`/`AssociationParent/Content`, because the reference pass cannot carry a
  non-encrypt action.
- **New Amadeus paths.** The `FP` and `OS` `dataElementsIndiv` free-text nodes gain coverage.

No engine change, no schema change, no new `PiiType`. The whole change is baked-ruleset authoring plus
contract tests over sanitized fixtures.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `pii-rules`: defines which non-passenger persons and which pseudonymous identifiers are in scope,
  and requires free-text identity-document spans to use format-preserving sentinels.
- `amadeus-pii-baseline`: gains orderer-name, remark date-of-birth/gender, employee-id, profile-ref
  and loyalty-pref rules, plus first-time coverage of the `FP` and `OS` free-text elements.
- `sabre-pii-baseline`: gains third-party name/phone rules, remark identity-document rules that also
  cover the two history mirrors, card-fragment rules for history nodes, and employee/traveller-profile
  id rules.
