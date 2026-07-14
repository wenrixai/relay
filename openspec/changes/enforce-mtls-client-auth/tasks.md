# Tasks — enforce mTLS client authentication

## 1. Failing tests first (TDD)

- [x] 1.1 `tests/unit/test_main_startup.py`: basic auth disabled + mTLS disabled + no other mechanism → `validate_auth_config` aborts startup.
- [x] 1.2 `tests/unit/test_main_startup.py`: `mtls_enabled=true` with missing CA/cert/key material → abort startup with a clear error.
- [x] 1.3 `tests/unit/test_main_startup.py`: basic auth disabled + mTLS fully configured → startup succeeds (mechanism enforced).
- [x] 1.4 `tests/unit/test_admin.py`: `/admin/flare` reports mTLS active ONLY when material present + enforced; reports inactive when only the flag is set.
- [ ] 1.5 `tests/e2e/`: with mTLS enabled, a request without a client cert is rejected; a request with a cert signed by the configured CA passes (use an in-fixture throwaway CA, no network).

## 2. Fail-closed guard (ship first)

- [x] 2.1 Generalize `auth_active(settings)` (middleware/auth.py) to "some client-auth mechanism is enforceable": basic-auth-with-creds OR mTLS-with-complete-material.
- [x] 2.2 Update `validate_auth_config` (main.py) to abort when no mechanism is enforced and none is explicitly disabled-with-intent; keep the existing basic-auth message path.

## 3. mTLS settings

- [x] 3.1 Add validated mTLS material settings (CA bundle path, server cert/key paths) to `Settings`; validate existence/readability at load when `mtls_enabled`.

## 4. Enforcement wiring

- [x] 4.1 `cli()` (main.py): when `mtls_enabled`, pass `ssl_certfile`/`ssl_keyfile`/`ssl_ca_certs`/`ssl_cert_reqs=CERT_REQUIRED` to `uvicorn.run()`; bind on `tls_port`.
- [ ] 4.2 Ensure health probes remain reachable per the existing probe policy (confirm probe scheme in the chart).

## 5. Diagnostics

- [x] 5.1 Derive `/admin/flare`'s mTLS-active value from the same predicate used by `validate_auth_config` (never the raw flag).

## 6. Deployment + docs

- [ ] 6.1 Helm chart: mount CA/cert/key from a Secret; wire probes to the correct port/scheme.
- [ ] 6.2 Document the mTLS opt-in and material in `docs/` (and note the private key stays on Wenrix servers).

## 7. Verify

- [x] 7.1 Targeted suites green.
- [x] 7.2 `just ci` green (lint + fmt + types + pylint + full test + coverage).
