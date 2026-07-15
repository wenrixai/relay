## Why

The relay currently fetches PII rules from a remote `RELAY_RULES_API_URL` at startup, falling back
to a baked bundle only on fetch/validation failure. The remote rules-API contract (§8.8, D7) is a
documented assumption pending O3 and adds runtime dependency, network risk, and startup latency for
a value that only changes at deploy time. Rules should always load from the local baked bundle
(`rules_fallback.json`) — the fallback becomes the only path.

## What Changes

- **BREAKING**: Remove the remote rules fetch entirely. Rules load exclusively from the baked
  `rules_fallback.json` bundle shipped in the image; there is no runtime HTTP call to a rules API.
- Remove `RELAY_RULES_API_URL` / `Settings.rules_api_url` (and its URL-scheme validator) — no
  replacement setting.
- Simplify `pii/rules_loader.py`: drop `_fetch_rules`, the `httpx.AsyncClient`/`url` parameters on
  `load_rules`, and the try-fetch-then-fallback branching. `load_rules` (or its replacement) only
  loads and validates the baked bundle; invalid bundle still aborts startup when any channel has PII
  enabled, matching current fail-closed behavior.
- Update `main.py` lifespan wiring to drop the client/url arguments to the rules loader call.
- Remove `rules_api_url_configured` from `/admin/flare` diagnostics output (no longer a meaningful
  toggle).
- Update tests, fixtures, and env-var references (`RELAY_RULES_API_URL`) across unit/integration/e2e
  suites that assumed a fetch path.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `pii-rules`: "Startup fetch with baked fallback" requirement replaced by a local-only load
  requirement — no fetch, no `RELAY_RULES_API_URL`, no "fetch failure falls back" scenario.
- `relay-configuration`: PII configuration settings requirement drops `RELAY_RULES_API_URL`; URL
  field validation requirement drops the rules-URL scheme check.

`admin-diagnostics` is impacted at the code level (the `rules_api_url_configured` field disappears
from `/admin/flare` output) but its spec requirement ("safe scalar values only", no field-by-field
enumeration) already covers this without wording changes, so no delta spec is needed there.

## Impact

- Code: `src/channel_relay/pii/rules_loader.py`, `src/channel_relay/settings.py`,
  `src/channel_relay/main.py`, `src/channel_relay/admin.py`.
- Config: `RELAY_RULES_API_URL` env var removed; generated JSON Schema for settings changes.
- Tests: `tests/unit/test_pii_rules_loader.py`, `tests/unit/test_settings_validation.py`,
  `tests/unit/test_admin.py`, and integration/e2e tests that set/unset `RELAY_RULES_API_URL`.
- Docs: `docs/PROJECT.md` §8.8/D7 references to the rules-API fetch.
- No dependency removal expected (`httpx` stays in use for upstream forwarding).
