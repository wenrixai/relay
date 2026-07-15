## Context

`pii/rules_loader.py` currently implements a two-tier load: attempt one HTTP `GET` against
`Settings.rules_api_url` with a 5s timeout, and on any failure (network, HTTP status, schema
validation) fall back to the baked `rules_fallback.json` resource. `main.py`'s lifespan calls
`load_rules(client, settings.rules_api_url, pii_required=...)`. This is a small, self-contained
subsystem (one module owns fetch + fallback), so the change is mechanical: delete the fetch branch,
keep the fallback branch as the only path, and remove the now-dead `url`/`client` plumbing and the
`rules_api_url` setting everywhere it's threaded through (settings, main.py wiring, admin diagnostics,
tests, docs).

## Goals / Non-Goals

**Goals:**
- Rules load only from the baked `rules_fallback.json` bundle — no network call, ever.
- Preserve existing fail-closed behavior: an invalid baked bundle still aborts startup when any
  channel has PII enabled; without PII it degrades to "no rules loaded" (unchanged).
- Remove all now-unused surface: `RELAY_RULES_API_URL` setting + validator, `httpx.AsyncClient`
  parameter on the loader, `rules_api_url_configured` admin field, and the `_fetch_rules` function.
- Keep the `rules_version`/`rule_version` gauge behavior identical (still set from the baked bundle).

**Non-Goals:**
- Not changing the baked bundle's schema, validation, or `RuleSet` model (`pii/rules.py` untouched).
- Not adding a new mechanism for updating rules at runtime (e.g. rebuild-and-redeploy stays the only
  update path, which is the intended replacement for remote fetch).
- Not touching unrelated `rules_fallback.json` content — only the loading mechanism.

## Decisions

- **Delete the fetch path rather than feature-flag it.** The relay's own guardrails already forbid
  keeping dead/optional code paths and feature-flag shims for behavior that's been fully decided
  (`CLAUDE.md` golden rules). Since remote fetch is being removed outright (not made configurable),
  a flag would be an unused abstraction.
- **Rename `load_rules` is optional; keep the name.** `load_rules(pii_required=...) -> RuleSet |
  None` remains the public entry point so `main.py`'s call site only drops two now-unused arguments
  instead of renaming across the codebase. `load_baked_rules()` stays as the low-level parse-only
  helper used directly by `tests/deployment/test_perf_harness.py`.
- **Drop `httpx` import from `rules_loader.py`.** No other code in that module needs it once
  `_fetch_rules` is gone; `httpx` remains a project dependency for upstream forwarding elsewhere.
- **`Settings.rules_api_url` removed, not deprecated-but-ignored.** Per golden rules, no
  backwards-compatibility shim for a setting that no longer does anything — an operator who still
  sets `RELAY_RULES_API_URL` gets `extra="ignore"` behavior from `BaseSettings` (silently unused),
  which is acceptable since it was already optional and defaulted to `None`.
- **`/admin/flare` drops `rules_api_url_configured` rather than hardcoding `false`.** The field
  described a fetch capability that no longer exists; keeping a permanently-false field would be
  misleading diagnostic output.

## Risks / Trade-offs

- [Any deployment still setting `RELAY_RULES_API_URL` expecting a live fetch silently gets baked
  rules instead] → This is the intended outcome per the request; call out in the PR description /
  release notes as a behavior change. No runtime warning is added since the setting is fully removed
  (nothing left to check it against).
- [Docs/spec drift if `docs/PROJECT.md` §8.8/D7 aren't updated] → Tasks include updating the
  referenced doc sections alongside code.

## Migration Plan

- Single-PR change: remove code, settings, tests referencing fetch; update specs and docs in the
  same change. No phased rollout needed since this only removes a fetch that already degrades
  gracefully to the exact behavior being made permanent.
- Rollback: revert the commit/PR; no data migration or persisted state is involved.
