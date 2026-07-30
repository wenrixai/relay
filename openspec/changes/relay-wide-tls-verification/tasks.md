## 1. Settings

- [x] 1.1 Write failing unit test: `Settings().upstream_tls_verify is True`; `RELAY_UPSTREAM_TLS_VERIFY=false`
      → `False` (`tests/unit/test_settings_validation.py`).
- [x] 1.2 Add `upstream_tls_verify: bool = True` to `Settings` (`settings.py`) next to the upstream
      pool/retry block, with a comment stating it applies to every channel and must stay `true` in
      production.

## 2. Config model (hard removal)

- [x] 2.1 Write failing unit tests: a channel with `tls={"insecure_skip_verify": True}` raises
      `ValidationError` (unknown field), and the generated JSON Schema has no `ChannelTLS` definition
      (`tests/unit/test_config.py`); delete the old default/opt-out/unknown-subfield tests.
- [x] 2.2 Delete the `ChannelTLS` model and the `ChannelConfig.tls` field from `config/models.py`.

## 3. Single upstream client

- [x] 3.1 Write failing unit test: `build_http_client(Settings())` verifies TLS;
      `build_http_client(Settings(upstream_tls_verify=False))` does not (assert on the transport's
      SSL context, as the existing tests do) (`tests/unit/test_main_startup.py`).
- [x] 3.2 Change `build_http_client(settings)` to read `settings.upstream_tls_verify` and drop the
      `verify` keyword argument; update its docstring (single pool, one policy).
- [x] 3.3 Simplify `_build_upstream_clients` to build only `application.state.client` and return a
      single `owns_client` bool; delete the `insecure_tls_required` computation.
- [x] 3.4 Drop the insecure-client branches from `_instrument_http_clients` and
      `_uninstrument_http_clients`.
- [x] 3.5 Remove the `insecure_http_client` parameter (and its docstring entry) from `create_app`, and
      the `application.state.insecure_client` initialization.
- [x] 3.6 Update `lifespan` to unpack a single `owns_client` and close only that client.
- [x] 3.7 Remove the pool-selection ternary in the `relay()` route; forward with
      `request.app.state.client`.

## 4. Startup warning

- [x] 4.1 Write failing unit tests: a WARNING is logged when `upstream_tls_verify=False`, naming
      `RELAY_UPSTREAM_TLS_VERIFY` and stating all channels are affected; none when it is `True`.
- [x] 4.2 Rewrite `warn_insecure_tls_config` in `main.py` to take `Settings` and emit the single
      relay-wide warning; update the `_load_and_validate_startup_config` call site.

## 5. Integration

- [x] 5.1 Rewrite `tests/integration/test_tls_insecure_channel.py` as
      `tests/integration/test_tls_verification.py`: the shared client verifies by default; with
      `RELAY_UPSTREAM_TLS_VERIFY=false` it does not; every channel forwards through the one client;
      `app.state` exposes no `insecure_client`; `create_app(insecure_http_client=...)` raises
      `TypeError`.
- [x] 5.2 Grep for remaining `insecure_client` / `insecure_http_client` / `tls=` references across
      tests, fixtures, `deployment/relay.example.json`, and `perf/relay.perf.json`; remove them.

## 6. Spec sync

- [x] 6.1 Confirm the delta spec in `specs/relay-configuration/spec.md` matches implemented behavior
      (global toggle, single pool, channel `tls` block rejected).

## 7. Docs

- [x] 7.1 `docs/PROJECT.md` §5.1: replace the per-channel TLS sentence with the relay-wide setting.
- [x] 7.2 `docs/SECURITY_POSTURE.md` "Upstream TLS" bullet: single pool, relay-wide all-or-nothing
      opt-out, warned at startup, never in production.
- [x] 7.3 `docs/PROXY_CONFIGURATION_GUIDE.md`: document `RELAY_UPSTREAM_TLS_VERIFY` in the env-var
      reference and state that channel `tls` blocks are no longer accepted.

## 8. Verification

- [x] 8.1 `just ci` green (pre-commit, mypy strict, pylint, ruff, coverage ≥ 85%).
