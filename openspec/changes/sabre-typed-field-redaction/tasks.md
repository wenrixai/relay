## 1. Contract tests (TDD — write failing first)

- [ ] 1.1 Add a typed-field contract test that runs the sanitized `GetReservationRS` fixture through
  the redaction engine and asserts every redacted `DateOfBirth` parses via
  `ciso8601.parse_datetime_as_naive(...)` (same call the caller uses) — fails today because `*` mask
  is unparseable.
- [ ] 1.2 Extend the test to assert every redacted `Gender` is in the valid code set (`{"M","F",...}`
  as the caller accepts) and equals the sentinel `M`.
- [ ] 1.3 Extend the test to assert every redacted `ExpiryMonth`/`ExpiryYear` is all digits (no `*`)
  and length-preserved.
- [ ] 1.4 Confirm the new tests fail against the current ruleset (red step) and that existing Sabre
  golden tests still assert one-way (no `ENC_`) behavior for these fields.

## 2. Rule changes

- [ ] 2.1 Change `sabre.res.docs_dob` from `method: mask` to `method: replace` with
  `replacement: "1901-01-01"` in `rules_fallback.json`.
- [ ] 2.2 Change `sabre.res.docs_gender` from `method: mask` to `method: replace` with
  `replacement: "M"`.
- [ ] 2.3 Change `sabre.res.card_expiry` to keep `method: mask` but add `mask_char: "0"`.
- [ ] 2.4 Update any Sabre golden unit test that asserts the old `*`-mask output for these three
  fields to expect the new schema-valid values.

## 3. Verify & spec sync

- [ ] 3.1 Run `just test-fast` (then `just ci`) — all tests green, including the new contract tests.
- [ ] 3.2 Run `openspec validate sabre-typed-field-redaction` and confirm the delta specs pass.
- [ ] 3.3 Confirm the `pii-rules` ADDED requirement and `sabre-pii-baseline` MODIFIED requirements
  match the shipped rules (DOB replace / gender replace / expiry numeric mask).
