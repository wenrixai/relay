## 1. Red — failing tests

- [x] 1.1 `tests/unit/test_config.py`: loader error for invalid credential value never contains the
      value; exception has no cause chain; update `test_loader_aborts_on_invalid_config` to expect
      `ConfigValidationError`.
- [x] 1.2 `tests/unit/test_config.py`: duplicate channel names rejected (message names the
      duplicate); distinct names accepted.
- [x] 1.3 `tests/unit/test_config.py` / settings tests: port 0 and 65536 rejected; `proxy_pass`
      without `http(s)://` rejected, `http://mock:9000` accepted; `host` with scheme or path
      rejected; `rules_api_url` without scheme rejected.
- [x] 1.4 `tests/unit/test_main_startup.py`: startup WARNING emitted when `authorization.external`
      configured; no warning otherwise.
- [x] 1.5 `cli()` uvicorn kwargs test (monkeypatch `uvicorn.run`): `timeout_keep_alive=75`,
      `proxy_headers=True`, `forwarded_allow_ips="*"`, `server_header=False`.

## 2. Green — implementation

- [x] 2.1 `ConfigValidationError` + sanitized re-raise in `config/loader.py`
      (`errors(include_input=False, include_url=False)`, `raise ... from None`).
- [x] 2.2 Channel-name uniqueness `model_validator` on `RelayConfig`.
- [x] 2.3 Port range `Field(ge=1, le=65535)`; URL/host `field_validator`s (no `HttpUrl`).
- [x] 2.4 `warn_unenforced_config` called in lifespan after config load.
- [x] 2.5 uvicorn kwargs in `cli()`.

## 3. Verification

- [x] 3.1 `just ci` green (ruff, mypy strict, pylint, pytest + coverage gate).
- [x] 3.2 Spec delta matches implemented behavior.
