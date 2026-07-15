## 1. Rules loader

- [x] 1.1 Write/update failing test(s) in `tests/unit/test_pii_rules_loader.py` asserting
      `load_rules` takes no `client`/`url` args and never performs an HTTP call, loading only the
      baked bundle.
- [x] 1.2 In `src/channel_relay/pii/rules_loader.py`, remove `_fetch_rules`, the `httpx` import, and
      the `client`/`url` parameters from `load_rules`; keep `load_baked_rules()` unchanged and make
      it the sole source inside `load_rules`.
- [x] 1.3 Update the module docstring (currently describes "one startup fetch, baked fallback") to
      describe local-only loading.

## 2. Settings and wiring

- [x] 2.1 Remove `rules_api_url` field and its `_validate_rules_api_url` validator from
      `src/channel_relay/settings.py`.
- [x] 2.2 Update `src/channel_relay/main.py` lifespan to call the simplified `load_rules(
      pii_required=...)` (drop `application.state.client` and `settings.rules_api_url` args).
- [x] 2.3 No generated JSON Schema covers `Settings` (only `RelayConfig`/channels config has one, via
      `config/json_schema.py`), so there is nothing to regenerate here — the field removal from the
      pydantic model is sufficient.

## 3. Admin diagnostics

- [x] 3.1 Remove the `rules_api_url_configured` field from `src/channel_relay/admin.py`'s
      `/admin/flare` snapshot.
- [x] 3.2 Update `tests/unit/test_admin.py` to drop the `rules_api_url` setup and the
      `rules_api_url_configured` assertion.

## 4. Test and fixture cleanup

- [x] 4.1 Rewrite `tests/unit/test_pii_rules_loader.py` scenarios that exercise fetch
      success/failure/timeout paths; keep only baked-bundle success and invalid-bundle
      (PII required vs not) scenarios.
- [x] 4.2 Remove `rules_api_url` cases from `tests/unit/test_settings_validation.py`.
- [x] 4.3 Remove `RELAY_RULES_API_URL` env var references (`monkeypatch.delenv`/`setenv`) from
      `tests/integration/test_pii_sabre_relay.py`, `test_credential_config_validation.py`,
      `test_tls_insecure_channel.py`, `test_pii_amadeus_e2e.py`, `test_pii_travelfusion_relay.py`,
      `test_session_deanon_gate.py`, `test_pii_referential.py`, `test_pii_roundtrip.py`, and
      `tests/e2e/conftest.py` — these tests should rely on baked rules unconditionally.
      `test_pii_referential.py`/`test_pii_roundtrip.py` used a mocked rules API to inject custom
      fixture rulesets; switched those to monkeypatch `rules_loader._read_baked_text` instead.
- [x] 4.4 Update comments/docstrings in `tests/integration/test_pii_amadeus_e2e.py` and
      `tests/e2e/conftest.py` that explain the "no rules API configured → baked fallback" behavior
      to reflect that baked rules are now the only path.

## 5. Docs and spec sync

- [x] 5.1 Update `docs/PROJECT.md` §8.8/D7 to remove the remote rules-API fetch description.
- [x] 5.3 Discovered additional blast radius beyond the original plan: remove the Terraform
      `rules_api_url` variable and its conditional `RELAY_RULES_API_URL` container-env wiring
      (`deployment/terraform/variables.tf`, `main.tf`, `README.md`, `terraform.tfvars.example`),
      `docs/PROXY_CONFIGURATION_GUIDE.md`'s env var table row, and the channel-implementation skill
      reference doc's mention of the env var.
- [x] 5.2 Run `just cov` (or equivalent full local pipeline) to confirm the 85% coverage gate and
      all suites pass after removal. 535 passed, 95.53% coverage; `just lint`/`just types`/`just
      pylint` also green.
