# Tasks: add-sabre-pii-baseline

## 1. Fixtures

- [x] 1.1 Sanitize the eight `sabre/` payloads into `tests/fixtures/sabre/` (fake but
      shape-identical names/emails/phones/FF numbers/card fragments/tokens; truncate
      `DailySalesReportRS` to ~5 `IssuanceData` records; keep one file per operation:
      `get_reservation_response.xml`, `get_reservation_pq_history_response.xml`,
      `travel_itinerary_read_response.xml`, `get_price_quote_response.xml`,
      `get_price_quote_pqr_response.xml`, `air_ticket_emd_response.xml`,
      `daily_sales_report_response.xml`, `session_create_request.xml`)
- [x] 1.2 Verify no real PII/credentials remain in the sanitized fixtures (grep the original
      values); do not commit raw `sabre/` files

## 2. Shared golden-test helpers (DRY)

- [x] 2.1 Extract the keyring/ruleset/fixture-loading/`_texts` helpers from
      `tests/unit/test_pii_amadeus.py` into a shared module (e.g. `tests/unit/pii_golden.py`
      or conftest fixtures) and switch the Amadeus suite to it (behavior unchanged, suite green)

## 3. Baseline rules (failing tests first per group)

- [x] 3.1 Write failing golden tests for name redaction (text + attribute forms across
      GetReservationRS, GetPriceQuoteRS incl. embedded PriceQuoteInfo, AirTicketRS,
      DailySalesReportRS, TravelItineraryReadRS), then add the `sabre.*` name rules
      (shared pqs attribute rule with operation alternation) to `rules_fallback.json`
- [x] 3.2 Failing tests + rules for GetReservationRS contact/identity/loyalty: email (encrypt),
      phone (mask), address lines (mask), DOCS children (mask; dob/gender/person),
      DOCO free text (mask; visa), FrequentFlyer number (encrypt)
- [x] 3.3 Failing tests + rules for payment: or114 CardNumber text (live + History), pqs
      `Card/@number`, expiry month/year (mask), `BankIdentificationNumber` text, and the
      OB-fee Description BIN via `extract_patterns` (span-preserving)
- [x] 3.4 Failing tests + `reference` rules for remark/SSR free text (RemarkLine/Text,
      Generic/ServiceRequest FreeText+FullText) sourcing person/email/phone/frequent_flyer
- [x] 3.5 Non-PII preservation tests: record locators, UpdateToken, ticket/EMD/invoice numbers,
      amounts+currency, agent sines, PCC, DK/seat numbers, MessageHeader ids byte-identical
- [x] 3.6 Round-trip tests: every `encrypt` field decrypts back via `deanonymize_request_body`;
      masked fields are one-way; bump `rules_version` to `sabre+amadeus-baseline-<date>`

## 4. Integration (relay pipeline)

- [x] 4.1 Integration test `tests/integration/test_pii_sabre_relay.py` (basename unique vs unit
      suite): mock Sabre channel returns fixture responses; assert PII redacted end-to-end
      without rules API (baked fallback), counts in metrics
- [x] 4.2 Credential-swap coverage with real shapes: request `SessionCreateRQ` security header
      replaced by configured `soap_security` fragment (UsernameToken with unqualified
      Organization/Domain); response `wsse:BinarySecurityToken` becomes `ENC_` token and
      round-trips on the next request; ordering (cleanup before redaction) asserted

## 5. Close-out

- [x] 5.1 `just ci` green (lint, fmt, mypy, pylint, full test suite incl. timeouts); confirm
      generated rules JSON Schema unchanged (no model edits)
- [x] 5.2 Remove the raw `sabre/` payload folder from the working tree (or gitignore it) so
      unsanitized data is never committed
