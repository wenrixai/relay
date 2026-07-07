## 1. Settings

- [ ] 1.1 Add `channels_json: str | None = None` to `Settings` (`settings.py`), env `RELAY_CHANNELS_JSON`.
- [ ] 1.2 Update `settings.py` module docstring to note the new env-sourced channel config path and
      the secrets-visibility tradeoff (env vs. mounted file).

## 2. Loader

- [ ] 2.1 Add `load_relay_config(settings: Settings) -> RelayConfig` in `config/loader.py`: if
      `settings.channels_json` is set (non-empty), `json.loads` it and `RelayConfig.model_validate`,
      with the same failure-logging shape as `load_config` (log `error_type` only, never the raw
      value); else delegate to `load_config(settings.config_file)`.
- [ ] 2.2 Keep `load_config(path)` unchanged (still used directly by existing tests/call sites).

## 3. Startup wiring

- [ ] 3.1 Update `main.py` config-loading call site to use `load_relay_config(settings)` instead of
      `load_config(settings.config_file)`.
- [ ] 3.2 Update the readiness check (`main.py:84-87`, "config file not found" warning) to run only
      when `settings.channels_json` is unset — skip the file-existence check when env config is active.

## 4. Spec sync

- [ ] 4.1 Confirm delta spec in `specs/relay-configuration/spec.md` matches implemented behavior
      (precedence, invalid-config abort, skipped readiness check).

## 5. Tests

- [ ] 5.1 Unit test: `RELAY_CHANNELS_JSON` set with valid JSON → `load_relay_config` returns expected
      `RelayConfig`, `config_file` never read (e.g. point `config_file` at a nonexistent path to prove
      it's untouched).
- [ ] 5.2 Unit test: `RELAY_CHANNELS_JSON` unset → falls back to `load_config(settings.config_file)`
      (existing file-based behavior unchanged).
- [ ] 5.3 Unit test: `RELAY_CHANNELS_JSON` set to invalid JSON → raises, logs only `error_type`, never
      the raw value (assert on captured log record).
- [ ] 5.4 Unit test: `RELAY_CHANNELS_JSON` set to valid JSON that fails `RelayConfig` validation →
      raises `pydantic.ValidationError`, logs only `error_type`.
- [ ] 5.5 Unit test: readiness check does not warn "config file not found" when `RELAY_CHANNELS_JSON`
      is set and `config_file` path does not exist.
- [ ] 5.6 Update/add `just ci` coverage: run full suite green, `mypy` strict, `pylint`, `ruff`
      lint+format pass on `settings.py`, `config/loader.py`, `main.py`.

## 6. Docs

- [ ] 6.1 Document `RELAY_CHANNELS_JSON` in relevant deployment/config docs (README or
      `openspec/specs/relay-configuration/spec.md`-adjacent docs), including the env-visibility vs.
      file-permission tradeoff for channels containing `credentials` secrets.
