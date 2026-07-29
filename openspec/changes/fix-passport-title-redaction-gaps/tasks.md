## 1. Fixtures reproduce the leaks (TDD)

- [x] 1.1 Extend `stl19:DOCSEntry` in `tests/fixtures/sabre/get_reservation_pq_history_response.xml` with `DocumentType`, `CountryOfIssue`, `DocumentNumber`, `DocumentNationalityCountry`, `DocumentExpirationDate` (ISO), in real payload element order.
- [x] 1.2 Extend `or114:TravelDocument` in the same fixture with `DocumentIssueCountry`, `DocumentNumber`, `DocumentNationalityCountry`, `DocumentExpirationDate` (`DDMMMYYYY`), `PrimaryDocHolderInd`.
- [x] 1.3 Add a `DOCO` SSR to `tests/fixtures/amadeus/pnr_retrieve_response.xml` carrying visa free text.

## 2. Failing tests

- [x] 2.1 `test_pii_sabre.py`: passport number masked in all three locations; expiry replaced per-namespace sentinel; nationality replaced; document kind and other non-PII siblings survive.
- [x] 2.2 `test_pii_sabre_typed_fields.py`: make the date assertions namespace-aware — `stl19` dates parse as ISO, `or114` dates parse as `DDMMMYYYY`.
- [x] 2.3 `test_pii_amadeus.py`: DOCO free text masked and visa number gone; honorific redacted in both given-name fields and round-trips; bare given name still reference-scrubbed from the remark; counts updated.

## 3. Baked ruleset (rules_fallback.json)

- [x] 3.1 Widen `sabre.res.travel_document_number` to the `DOCSEntry` / `TravelDocument` / `OtherSupplementaryInformation` union.
- [x] 3.2 Add `sabre.res.docs_expiry` (ISO sentinel) and `sabre.res.docs_expiry_history` (`DDMMMYYYY` sentinel).
- [x] 3.3 Split `sabre.res.docs_dob`; add `sabre.res.docs_dob_history` with the `DDMMMYYYY` sentinel.
- [x] 3.4 Add `sabre.res.docs_nationality` over the four country nodes, pii type `nationality`.
- [x] 3.5 Add `amadeus.pnr.ssr_doco` for `DOCO`/`DOCA` free text, pii type `visa`.
- [x] 3.6 Add `amadeus.pnr.name_title`, pii type `gender`, over both given-name fields.
- [x] 3.7 Bump `rules_version` to `…-baseline-2026-07-29`.

## 4. Verify

- [x] 4.1 `uv run pytest tests/unit tests/integration` green.
- [x] 4.2 Re-run redaction over the three reported defect payload shapes: no reported value survives, operational codes do.
- [x] 4.3 `just ci` green (lint, format, mypy strict, pylint, coverage gate).
- [x] 4.4 `openspec validate fix-passport-title-redaction-gaps --strict`.
