## 1. Config model (hard removal)

- [x] 1.1 Write failing unit tests: a channel with `tls={"insecure_skip_verify": True}` raises
      `ValidationError` (unknown field), and the generated JSON Schema has no `ChannelTLS` definition
      (`tests/unit/test_config.py`); delete the old default/opt-out/unknown-subfield tests.
- [x] 1.2 Delete the `ChannelTLS` model and the `ChannelConfig.tls` field from `config/models.py`.

## 2. Single, always-verifying upstream client

- [x] 2.1 Write failing unit test: the client built by `build_http_client(Settings())` verifies TLS,
      and `build_http_client` accepts no `verify` argument (`tests/unit/test_main_startup.py`);
      delete the `verify=False` test.
- [x] 2.2 Drop the `verify` keyword from `build_http_client` and let httpx's verifying default stand;
      update its docstring (one pool, verification not configurable).
- [x] 2.3 Simplify `_build_upstream_clients` to `_build_upstream_client`: build only
      `application.state.client` and return a single `owns_client` bool.
- [x] 2.4 Drop the insecure-client branches from `_instrument_http_clients` and
      `_uninstrument_http_clients`.
- [x] 2.5 Remove the `insecure_http_client` parameter (and its docstring entry) from `create_app`, and
      the `application.state.insecure_client` initialization.
- [x] 2.6 Update `lifespan` to unpack a single `owns_client` and close only that client.
- [x] 2.7 Remove the pool-selection ternary in the `relay()` route; forward with
      `request.app.state.client`.

## 3. Startup warning removal

- [x] 3.1 Delete the `warn_insecure_tls_config` tests — with no opt-out there is nothing to warn about.
- [x] 3.2 Delete `warn_insecure_tls_config` from `main.py` and its `_load_and_validate_startup_config`
      call site; leave `warn_unenforced_config` untouched.

## 4. Integration

- [x] 4.1 Rewrite `tests/integration/test_tls_insecure_channel.py` as
      `tests/integration/test_tls_verification.py`: the shared client verifies; every channel forwards
      through that one client; `app.state` exposes no `insecure_client`;
      `create_app(insecure_http_client=...)` raises `TypeError`.
- [x] 4.2 Grep for remaining `insecure_client` / `insecure_http_client` / `tls=` references across
      tests, fixtures, `deployment/relay.example.json`, and `perf/relay.perf.json`; remove them.

## 5. Spec sync

- [x] 5.1 Confirm the delta spec in `specs/relay-configuration/spec.md` matches implemented behavior
      (mandatory verification, no opt-out setting, single pool, channel `tls` block rejected).

## 6. Docs

- [x] 6.1 `docs/PROJECT.md` §5.1: state that upstream TLS verification is mandatory and not a channel
      setting.
- [x] 6.2 `docs/SECURITY_POSTURE.md` "Upstream TLS" bullet: always verifying, single pool, no opt-out
      at any level; private-CA upstreams are a trust-store problem.
- [x] 6.3 `docs/PROXY_CONFIGURATION_GUIDE.md`: state that channel `tls` blocks are no longer accepted
      and that no setting disables verification.

## 7. Verification

- [x] 7.1 `just ci` green (pre-commit, mypy strict, pylint, ruff, coverage ≥ 85%).
