## 1. Failing tests first (TDD)

- [x] 1.1 Add Amadeus fixture + tests (`tests/fixtures/amadeus/pnr_retrieve_contact_remarks_response.xml`, `TestContactRemarks` in `test_pii_amadeus.py`) asserting remark-only names, `*ARR*`/`NAME-` lines, and ECTC emergency-contact name+phones are scrubbed and round-trip.
- [x] 1.2 Add Sabre fixture + tests (`tests/fixtures/sabre/get_reservation_history_contacts_response.xml`, `TestGetReservationHistoryAndContacts` in `test_pii_sabre.py`) covering payment/history names, contact + obfuscated emails, CTC/agency/ReceivedFrom phones, traveller ids, whole-node history phone masking, and the word-boundary limitation.
- [x] 1.3 Add engine token-integrity tests (`TestTokenIntegrity` in `test_pii_engine.py`): extraction and reference matching must not rewrite inside an existing `ENC_` token.
- [x] 1.4 Update the Amadeus golden name test for honorific-preserving given-name extraction.

## 2. Token-integrity guard (engine)

- [x] 2.1 Add `_token_spans` and shield extraction spans (`_extract_spans` seeds `occupied` with token spans).
- [x] 2.2 Add `_reference_sub` (module-level, no loop closures) that skips matches overlapping an existing token; use it in `_redact_reference_rule`.

## 3. Baked ruleset coverage (rules_fallback.json)

- [x] 3.1 Amadeus: given-name honorific-preserving extraction; remark name-line / `*ARR*` / `/N-` name extraction; remark phone extraction (incl. `MOB`-glued).
- [x] 3.2 Sabre structured: encrypt `PassengerName` + `Passengers/Name`; add `PassengerContactEmail/Email`; mask whole history phone nodes (`AssociationChild[Type='PhoneNumber']/Content`, `HistoryAssociationElement[@Type='PHONE_NUMBER']`).
- [x] 3.3 Sabre reference: extend the `GetReservationRS` reference rule to `Content`, `HistoryAssociationElement`, `AccountingLineText`, `or114:Comment`.
- [x] 3.4 Sabre extraction: `¤`/`//`-obfuscated contact emails (incl. `or114:Comment`, CTCE service requests); `CTC*` special-request phones; agency-remark phones; corporate booking-tool traveller ids; `ReceivedFrom` embedded phones.

## 4. Verify

- [x] 4.1 `uv run pytest tests/unit` green (484 tests).
- [x] 4.2 Re-run redaction over the captured un-anonymized `PNR_Reply` / `GetReservationRS` review-pack bodies: no known PII value survives, and the redacted body de-anonymizes cleanly across 300 randomized-IV trials per channel.
- [x] 4.3 `ruff format --check`, `ruff check`, `mypy` strict, `pylint` (10.00) all green.
- [x] 4.4 `openspec validate expand-pnr-remark-pii-coverage --strict`.
