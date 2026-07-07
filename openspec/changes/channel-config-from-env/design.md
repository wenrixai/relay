## Context

`load_config` (`src/channel_relay/config/loader.py:18`) reads `settings.config_file` from disk, parses
JSON, and validates against `RelayConfig`. `main.py:84-87` checks the file exists at readiness time
and warns "Config file not found; relay not ready" if missing. `Settings` (`settings.py`) already
carries a precedent for this: `pii_keyring` (inline) vs. `pii_keyring_file` (path) — one config value,
two sources, env decides which wins.

## Goals / Non-Goals

**Goals:**
- Let operators supply the full channel config document via a single env var
  (`RELAY_CHANNELS_JSON`) when a mounted file isn't available.
- Keep file-based loading as the unchanged default — zero behavior change for existing deployments.
- Keep validation, abort-on-invalid-config, and never-log-secrets behavior identical regardless of
  source.

**Non-Goals:**
- No new secrets-handling primitive (e.g., no separate secret-ref indirection inside channel
  `credentials`). This change does not make env-sourced config more secure than file-sourced config —
  it only adds a second transport for the same trust-level document.
- No support for partial/merged sources (env overlaying file, or per-channel env vars). Precedence is
  whole-document, all-or-nothing: env present → use env; else → use file.
- No change to `RELAY_PII_KEYRING`/`RELAY_PII_KEYRING_FILE` precedent pattern beyond following it.

## Decisions

**1. New setting `channels_json: str | None` (env `RELAY_CHANNELS_JSON`), not overloading `config_file`.**
Mirrors the existing `pii_keyring` / `pii_keyring_file` split — one inline-value field, one
path field, same precedence idiom already used and tested in this codebase. Alternative considered:
make `config_file` itself accept either a path or raw JSON (sniff by first non-whitespace char) —
rejected as implicit/surprising; an explicit second field is unambiguous and matches an established
pattern reviewers already recognize.

**2. Precedence: `RELAY_CHANNELS_JSON` set → parse it; else → read `config_file` from disk.**
Simple, total ordering, no merge logic. Matches the `pii_keyring`/`pii_keyring_file` precedent exactly
(inline wins if both set — see `main.py:49-50` `inline=settings.pii_keyring, file_path=settings.pii_keyring_file`).

**3. `load_config` gains a `Settings`-aware entry point rather than changing its file-reading signature.**
Keep `load_config(path)` doing exactly what it does today (read a path, parse, validate) — used
directly by existing tests. Add a thin wrapper, e.g. `load_relay_config(settings: Settings) ->
RelayConfig`, that branches on `settings.channels_json` and either `RelayConfig.model_validate(json.loads(...))`
directly or delegates to `load_config(settings.config_file)`. `main.py` calls the wrapper. Alternative
considered: mutate `load_config` to accept `str | Path | None` plus an env override — rejected, it
would blur "path" and "content" through one parameter and complicate the existing file-not-found
readiness check, which only makes sense for the file path.

**4. File-not-found readiness warning (`main.py:84-85`) only applies when the file path is actually
the active source.** When `RELAY_CHANNELS_JSON` is set, skip the file-existence check entirely — the
file may legitimately not exist in that deployment mode.

**5. Failure logging stays identical to `loader.py:31-34`: log `error_type`, never the raw value.**
This already holds for the file path (raw file contents, which may contain `credentials`, are never
logged). The env path gets the same treatment — never log `settings.channels_json` on parse/validation
failure, only the exception type.

**6. Document, don't engineer around, the env-visibility tradeoff.** `ChannelConfig.credentials`
values are already embedded in the config document today, file or env. Env vars are more exposed
to local inspection (`/proc/<pid>/environ`, orchestrator dashboards) than a file with restricted
permissions. This change doesn't add a new secret-in-config exposure (that already exists via the
credentials block); it changes the transport's visibility profile. Spec and docs state this so
operators choose deliberately — no code-level mitigation is in scope here (e.g., no secret-ref
indirection — that would be a separate, larger change).

## Risks / Trade-offs

- **[Risk]** Large channel configs in an env var may hit orchestrator env-size limits (e.g.,
  Kubernetes ConfigMap/env size limits, shell `ARG_MAX` in some launchers) → **Mitigation**: none
  needed in-code; document the limit consideration, file-based config remains available and is the
  documented default for large channel sets.
- **[Risk]** Operators may assume env-sourced config is "more secure" than file-sourced (common
  12-factor intuition) when for credential-bearing channel config the reverse can be true (env is
  more visible to process/orchestrator introspection) → **Mitigation**: explicit spec scenario +
  docs callout stating the tradeoff plainly.
- **[Risk]** Divergent behavior between env and file paths if the wrapper logic drifts →
  **Mitigation**: single wrapper function is the only call site in `main.py`; tests cover both
  branches with the same validation assertions.

## Migration Plan

- Purely additive: no existing deployment sets `RELAY_CHANNELS_JSON`, so behavior is unchanged until
  an operator opts in.
- Rollback: unset `RELAY_CHANNELS_JSON`; relay falls back to `config_file` as before.

## Open Questions

None — precedence, logging, and failure-mode questions are resolved above by following the existing
`pii_keyring`/`pii_keyring_file` precedent.
