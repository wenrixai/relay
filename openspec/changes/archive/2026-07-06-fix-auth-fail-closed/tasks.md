## 1. Failing tests first (TDD red)

- [x] 1.1 Add `tests/unit/test_main_startup.py`: assert startup aborts with `RuntimeError`
  when `basic_auth_enabled=True` and creds unset (mirror
  `test_startup_aborts_when_pii_enabled_without_keyring`).
- [x] 1.2 Add tolerant cases: boots when `basic_auth_enabled=False`, and when both creds set.
- [x] 1.3 Run the new tests, confirm they fail (red) before implementation.

## 2. Implementation (green)

- [x] 2.1 In `src/channel_relay/main.py`, add a `validate_auth_config(settings)` helper that
  raises `RuntimeError` when `settings.basic_auth_enabled and not auth_active(settings)`.
- [x] 2.2 Call it in the lifespan before `build_keyring` (~`main.py:105`); import
  `auth_active` from `channel_relay.middleware.auth`.
- [x] 2.3 Correct the `auth_active` docstring in `src/channel_relay/middleware/auth.py`
  (no longer "serves open" / "logs at startup" on missing creds).

## 3. Fix test blast radius

- [x] 3.1 Set `basic_auth_enabled=False` in `tests/e2e/conftest.py` `e2e_client` builder.
- [x] 3.2 Set `basic_auth_enabled=False` in integration fixtures that hit `/channel`
  (`test_pii_sabre_relay.py`, `test_pii_referential.py`, `test_credential_swap_forwarder.py`,
  and any others found).

## 4. Verify

- [x] 4.1 `just test-fast`, then `just ci` — all green.
- [x] 4.2 `openspec validate fix-auth-fail-closed --strict` passes.
- [x] 4.3 Manual smoke: default env with no creds → `just run` crashes on startup with the
  new error; does not serve `/channel`.

## 5. Archive

- [x] 5.1 Archive the change to fold the delta into `openspec/specs/client-authentication`.
