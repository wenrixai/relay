## 1. Sanitized evidence

- [x] 1.1 Add `tests/fixtures/amadeus/pnr_retrieve_third_party_remarks_response.xml` — trimmed
  `PNR_Reply` keeping both RM remark mirrors, the `FP` and `OS` `dataElementsIndiv`, and the structured
  traveller name so the reference pass has a bucket.
- [x] 1.2 Add `tests/fixtures/sabre/get_reservation_third_party_remarks_response.xml` — trimmed
  `GetReservationRS` keeping the passenger coded-remark block, reservation `HS`/`INVOICE`/`CODED`
  lines, `ReceivedFrom`, `FutureTicketing`, the `CTC` phone nodes, both profile namespaces, and three
  history transactions so `HistoryAssociationElement` and both `Association*/Content` are exercised.
  Preserve the `¤` and `¥` delimiters verbatim.
- [x] 1.3 Delete the raw captured payloads and add them to `.gitignore` (live passenger data and a live
  Sabre `BinarySecurityToken`).

## 2. Failing tests first (TDD)

- [x] 2.1 `TestThirdPartyRemarks` in `test_pii_amadeus.py`: orderer name in both mirrors, remark
  date-of-birth/gender sentinels, employee id, profile ref, loyalty pref, `FP` card + expiry, `OS`
  contract number; round-trip; template remark and organisation codes preserved.
- [x] 2.2 `TestThirdPartyRemarks` in `test_pii_sabre.py`: emergency contact name/phone,
  authority-to-charge, arranger via `CTC` phone / remark / invoice field / `ReceivedFrom` /
  `FutureTicketing`, remark passport/document-dates/nationality/date-of-birth/gender sentinels, history
  card fragment; agent name and sine preserved.
- [x] 2.3 Mirror test: the same sentinel appears in `RemarkLine/Text`, `HistoryAssociationElement`, and
  both `Association*/Content` — the regression a reference-rule-only fix would miss.
- [x] 2.4 Token-identity test: the arranger name collected from the `CTC` phone node yields the same
  token in the remark, invoice field and ticketing comment.
- [x] 2.5 Rule-ordering regression test: the `CTC` arranger name is tokenized, not swallowed by the
  whole-node phone rule — fails if the rule is moved after it.
- [x] 2.6 Operational-survival negatives: agent name and sine, record locators, ticket numbers, fares,
  policy blocks, corporate account/tour/discount codes, and the corporate URL are byte-present.
- [x] 2.7 Relay-level case per channel in `tests/integration/test_pii_extended_operations_relay.py`.

## 3. Rules

- [x] 3.1 Amadeus: orderer name, remark date-of-birth, remark gender, employee id, profile ref, loyalty
  pref on the existing RM triple path; patterns anchored without the leading `*`.
- [x] 3.2 Amadeus: new `FP` card + expiry rules and new `OS` contract-number rule.
- [x] 3.3 Sabre: third-party name and phone rules on the remark path.
- [x] 3.4 Sabre: `ctc_arranger_name` inserted **before** `sabre.res.phone`; `received_from_arranger`;
  `future_ticketing_name`.
- [x] 3.5 Sabre: remark date-of-birth, gender, passport, document dates, nationality and card-fragment
  rules, each unioning the remark path with `HistoryAssociationElement` and both `Association*/Content`.
- [x] 3.6 Sabre: employee-id (attribute + remark) and traveller-profile-id rules.
- [x] 3.7 Add `//s19:Comment` to `sabre.res.remarks_reference` so collected third-party names reach the
  ticketing comment.
- [x] 3.8 Bump `rules_version`.

## 4. Regression sweep

- [x] 4.1 Re-derive the `counts` assertions in `test_pii_amadeus.py`, `test_pii_sabre.py`,
  `test_pii_amadeus_coverage_gaps.py` and `test_pii_sabre_coverage_gaps.py` that shift because the new
  marker patterns fire on existing fixtures. Derive each number from the engine.
- [x] 4.2 Confirm no new rule fires on an operational-only fixture (`queue_access_response.xml` stays
  uncovered; locators and ticket numbers unchanged everywhere).

## 5. Close out

- [x] 5.1 Replay both raw payloads through the engine: no plaintext third-party PII, identity-document
  data or person-linked identifier survives; agent names, fares and organisation codes do survive.
- [x] 5.2 Tests green (692 passed), `just types` clean, coverage 95.8% (gate 85%). NOTE: `just lint`
  and `just fmt-check` are red, but identically so on pristine `master` — 40 `ruff check` violations
  and 4 unformatted files, none in code this change touches. Pre-existing, tracked separately; this
  change adds no new violations.
- [ ] 5.3 Conventional commit; sync specs and archive the change.
