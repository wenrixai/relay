# Tasks: slice-3-channel-credential-swap

## 1. Spec and fixtures

- [x] 1.1 Add OpenSpec deltas for channel credential swap, error contract, transparent relay, and
      relay configuration.
- [x] 1.2 Add sanitized channel fixtures for request/response swap expectations.

## 2. Channel abstraction and parsers

- [x] 2.1 TDD red: registry and body-derived operation parser tests for every channel family.
- [x] 2.2 Implement channel handler protocol, registry, shared XML helpers, and per-channel
      operation parsers.

## 3. Request credential swap

- [x] 3.1 TDD red: channel-level request swap tests for Travelfusion, BA, LA, Farelogix,
      Amadeus/Sabre/Travelport.
- [x] 3.2 Implement structural request swaps and `credential_swap_failed` error handling.
- [x] 3.3 Wire swap into the forwarder after request de-anonymization and before upstream
      forwarding.

## 4. Response handling

- [x] 4.1 TDD red: Travelfusion response login removal and Sabre/Amadeus response auth encryption.
- [x] 4.2 Implement response swap hooks before PII redaction.

## 5. Close-out

- [x] 5.1 Update spec/config examples for Slice 3 credential keys.
- [x] 5.2 Run focused tests, `uv run pytest`, lint/type/pylint/pre-commit.
- [x] 5.3 Archive OpenSpec change after validation and implementation.
