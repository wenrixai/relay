## Why

Channel definitions (`RelayConfig`/`ChannelConfig`) load only from a JSON file at
`settings.config_file` (`/etc/wenrix/relay.json` by default). Some deployment targets (12-factor
PaaS, ephemeral containers, CI-driven canaries) cannot mount a file but can inject env vars. There is
currently no supported way to supply channel config without a mounted file.

## What Changes

- Add `RELAY_CHANNELS_JSON` env var: when set, its value is parsed as the same JSON document
  `load_config` currently reads from a file (a `RelayConfig`-shaped object), and takes precedence
  over `settings.config_file`.
- File-based loading remains the default and unchanged when `RELAY_CHANNELS_JSON` is unset —
  **no breaking change** to existing deployments.
- `load_config` gains a source-selection step: env var present → parse from env string; else →
  read `config_file` from disk (existing behavior unchanged, including "file not found" startup
  warning).
- Startup validation/abort-on-invalid-config behavior applies identically to the env-sourced path
  (same `RelayConfig.model_validate`, same logged error shape — never logs the raw value on failure,
  since the raw value may contain `credentials` secrets).
- Document the secrets tradeoff explicitly: `ChannelConfig.credentials` values are already
  embedded in channel config today regardless of source (file or env) — this change does not add a
  new secrets-in-config exposure, but env vars are visible via process inspection
  (`/proc/<pid>/environ`, orchestrator API) more readily than a file with restricted permissions.
  Docs/spec will state this tradeoff so operators choose consciously; no code enforcement is added
  beyond what already exists for the file path (both are "trusted input," not "hardened against
  local inspection").

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `relay-configuration`: add a `RELAY_CHANNELS_JSON` env-sourced config path as an alternative to
  the JSON config file, with defined precedence and identical validation/failure behavior.

## Impact

- `src/channel_relay/settings.py`: new optional `channels_json: str | None` field (`RELAY_CHANNELS_JSON`).
- `src/channel_relay/config/loader.py`: `load_config` (or a new wrapper) branches on env var
  presence before reading the file.
- `src/channel_relay/main.py`: startup config-loading call site passes `Settings` (or the resolved
  source) instead of only `settings.config_file`; "config file not found" readiness check only
  applies to the file path, not the env path.
- `openspec/specs/relay-configuration/spec.md`: new requirement/scenarios for env-sourced channel
  config and precedence.
- Docs: note the secrets-visibility tradeoff for `RELAY_CHANNELS_JSON` vs. mounted file.
- Tests: unit tests for precedence (env set vs. unset), env-sourced invalid JSON/invalid model abort
  behavior, and that no channel config value is ever logged on failure.
