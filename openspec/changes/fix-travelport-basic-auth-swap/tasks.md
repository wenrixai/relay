## 1. Red — fixtures and failing contract tests

- [x] 1.1 Replace the inaccurate `tests/fixtures/travelport/request.xml` WS-Security sample with a
  sanitized Travelport `PingReq`, and add production-shaped sanitized `BookingStartRsp` plus
  session-follow-up fixtures containing the same fake token in `SessTok/@id` and `@SessionKey`;
  validate them with the hardened parser and verify no real credential, branch, PII, or token remains.
- [x] 1.2 Add failing handler unit tests in `tests/unit/test_channel_credential_swap.py` for exact
  `Basic base64("Universal API/<username>:<password>")` construction, case-insensitive replacement
  of multiple caller `Authorization` variants, disabled-swap no-op, SOAP operation parsing, and
  no-op request-body swapping.
- [x] 1.3 Add failing Travelport response unit tests for `SessionKey` and `SessTok/@id` encryption,
  already-`ENC_` idempotence, unrelated `id` preservation, missing-keyring failure, and
  `requires_response_keyring` behavior independent of `pii.enabled`.
- [x] 1.4 Add failing configuration-load tests in
  `tests/integration/test_credential_config_validation.py` for a valid pair, each missing/empty field,
  colon/control-character rejection, obsolete `soap_*` key rejection, disabled-swap acceptance, and
  error messages that contain no supplied credential values.
- [x] 1.5 Add a failing mocked-forwarder integration test proving a stateless Travelport request
  reaches upstream with exactly one real Basic header, no caller header value, no injected
  `UsernameToken`, and semantically unchanged SOAP content.
- [x] 1.6 Add a failing `pii.enabled=false` session integration test: `BookingStartRsp/@SessionKey`
  is opaque to the caller, then the returned token replayed in both `SessTok/@id` and
  `@SessionKey` is restored to the original plaintext in both upstream locations with no `ENC_`
  residue.
- [x] 1.7 Add failing integration cases for a gzipped session replay and for response cleanup without
  a usable keyring, asserting gzip remains valid and plaintext session state is never returned on a
  fail-closed 502.
- [x] 1.8 Run only the new/changed tests and record that they fail for the expected missing Travelport
  header-auth/session-cleanup behavior, not for fixture, import, or environment errors.

## 2. Green — dedicated Travelport authentication

- [x] 2.1 Refactor `TravelportHandler` out of `SoapSecurityHandler`, retaining body-derived SOAP
  operation parsing while using a no-op credential body swap and leaving Amadeus/Sabre classes
  unchanged.
- [x] 2.2 Implement Travelport configuration validation for the required `username`/`password` pair,
  delimiter/control-character constraints, and obsolete SOAP-key rejection without exposing values.
- [x] 2.3 Implement standard-library Basic header construction with the required `Universal API/`
  prefix and `_set_header` case-insensitive replacement; preserve request-time
  `CredentialSwapError` defense in depth.
- [x] 2.4 Implement Travelport response-keyring gating and structural session cleanup for every
  `SessionKey` attribute plus only `SessTok/@id`, skipping already encrypted values and failing
  closed when encryption cannot complete.
- [x] 2.5 Run the focused handler, configuration, and forwarder tests until all new tests pass without
  changing their contract assertions.

## 3. Refactor — documentation and regression safety

- [x] 3.1 Remove Travelport from shared SOAP-security test parameterizations and add explicit
  regression assertions that existing Amadeus/Sabre static, dynamic, and session behavior is
  unchanged.
- [x] 3.2 Update `docs/CREDENTIAL_SWAP.md` and `docs/PROXY_CONFIGURATION_GUIDE.md` with the Travelport
  `username`/`password` migration, generated Basic format, keyring requirement, session round-trip,
  and a secret-safe configuration example; do not hand-edit generated schema.
- [x] 3.3 Review handler helpers and tests for full type hints, narrow exception handling, constant
  behavior across header casing, no body/header/credential logging, and no duplicate implementation
  that belongs in an existing safe helper.
- [x] 3.4 Run all credential-swap, session de-anonymization, header-hygiene, configuration, gzip, and
  error-contract test modules; confirm every test remains under the configured timeout and uses no
  real network.

## 4. Verify and hand off

- [x] 4.1 Run fixture leak probes against `tests/fixtures/travelport/` and confirm raw supplier
  payloads or live secrets are absent from the working tree.
- [x] 4.2 Run `openspec validate fix-travelport-basic-auth-swap --strict` and resolve every error.
- [x] 4.3 Run `just ci` (sync, ruff lint/format-check, mypy strict, pylint, full pytest, coverage) and
  resolve all failures without weakening tests or security constraints.
- [x] 4.4 Run the repository's required thermo-nuclear code-quality review for the non-trivial change
  and resolve high-confidence findings.
- [ ] 4.5 Prepare a migration note that calls out the breaking Travelport credential keys and keyring
  prerequisite, then archive the OpenSpec change only after implementation and review are complete.
