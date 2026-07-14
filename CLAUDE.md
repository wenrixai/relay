# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Agent/developer operating rules for the Wenrix Channel Relay (v2). This file is about how to work and
how the code is laid out, not the full requirements. Canonical requirements live elsewhere; read them
first:

- **`openspec/specs/`** — product, security, architecture, and configuration requirements
  (source of truth). Section refs like `§8.4` throughout the code point here / into `docs/PROJECT.md`.
- **`docs/PROJECT.md`** — engineering spec: pipeline design, token format, error contract, decisions.
- **`CONTRIBUTING.md`** — full workflow: Definition of Done, TDD, OpenSpec loop + exemptions, PR rules.

When code and `openspec/specs/` disagree, the spec wins: propose a change, do not drift.

## What this is
A transparent, privacy-first HTTP relay in front of travel channels (Sabre, Amadeus, Travelport,
Travelfusion, Farelogix, BA/LA NDC). The channel must never learn Wenrix is in the path. On the
**request** path it de-anonymizes `ENC_` PII tokens and swaps in channel credentials; on the
**response** path it encrypts (redacts) PII fields per rules. Credential swap and PII are opt-in per
channel; a zero-config channel is a straight pass-through.

## Golden rules
1. **Spec-driven + TDD.** Non-trivial work goes through the OpenSpec loop (details in
   `CONTRIBUTING.md`); write the failing test first. Exemptions (scaffold, typo, test-only, internal
   refactor) still need tests + green CI. Use OpenSpec only for meaningful spec-changing work — not
   chores or tiny bugfixes.
2. **No slow tests.** Every test finishes under the `pytest-timeout` (60s) and the `--fail-slow=500ms`
   gate. Mock the network.
3. **No retries.** Upstream calls fail fast; never add retry loops (the client owns retries). No
   periodic rule polling either — rules load once at startup.
4. **Never weaken crypto or leak secrets** (see Security below).
5. **Stay transparent.** The channel must never see Wenrix/forwarding/hop-by-hop headers or a
   `Server` header, and must receive de-anonymized (plaintext) requests.

## Commands
```bash
just ci            # full local pipeline (mirrors CI): sync + pre-commit + coverage
just test          # full suite, parallel (pytest -n auto --timeout=60)
just test-fast     # fast subset (excludes e2e)
just cov           # tests + coverage gate (fail-under 85%)
just lint / types / pylint / fmt-check   # individual gates
just run           # uvicorn channel_relay.main:app --reload
just up            # docker compose (relay + mock channels)
just helm-test     # helm lint + render + chart assertion tests (needs helm)
just perf          # k6 load harness against a local relay + mock (needs k6)
just docker-build  # multi-stage non-root Alpine runtime image

# single test / node:
uv run pytest tests/unit/test_forwarder.py::test_name
uv run pytest -k "sabre and swap"
uv run pytest -m "not e2e"           # markers: unit, integration, e2e

uv add <pkg>       # add a dependency (never pip); keep uv.lock committed
```

## Architecture (big picture)
Two config layers, an app factory, a handler registry, and a linear forward pipeline.

- **`main.py` — app factory + fail-closed startup.** `create_app()` builds the FastAPI app; all
  runtime state hangs off `app.state` (`config`, `keyring`, `client`, `rules`, `metrics`, `settings`).
  The `lifespan` performs startup validation that **aborts the process** on misconfig: basic-auth
  enabled without creds, credential-swap channel missing creds, PII enabled without a keyring, invalid
  config. Rules are fetched **once** here (baked fallback if the API is unreachable). Routes:
  `/liveness`, `/readiness` (503 + reasons until config loads), `/admin/flare` (auth'd redacted
  diagnostics), and `/channel/{name}` + `/channel/{name}/{path:path}` (both forms exist for v1 nginx
  parity). `cli()` runs uvicorn with `server_header=False`, `proxy_headers=True`, keep-alive > ALB idle.

- **Two config sources — keep them separate.**
  - `settings.py` → `Settings`: **process** config from `RELAY_*` env vars (port, auth toggle,
    timeouts, `max_inspect_bytes`, keyring material, `rules_api_url`, telemetry).
  - `config/models.py` → `RelayConfig`/`ChannelConfig`: the **channels** config from `relay.json`
    (loaded by `config/loader.py`). All pydantic v2; the JSON Schema is **generated** by
    `config/json_schema.py` — never hand-write it.

- **`proxy/forwarder.py` — this is the real request/response pipeline.** Despite `docs/PROJECT.md`
  §3.2 describing a `middleware/pipeline.py`, the ordered stages actually live as private functions
  inside `forward()`: `_authorization_stage` → `_request_credential_swap_stage` → `_request_pii_stage`
  (de-anonymize) → httpx forward (per-channel timeouts, `retries=0`) → `_response_pii_stage` (redact)
  → `_response_credential_swap_stage`. `find_channel`, `build_target_url`, gzip decode/encode, and
  header framing removal live here too. `middleware/` holds only cross-cutting pieces wired directly
  in `main.py`: `auth.py` (basic auth, constant-time), `header_hygiene.py`, `content.py`,
  `access_log.py`.

- **`channels/` — handler registry, NOT per-channel files.** `channels/__init__.py` maps each
  `ChannelType` to a handler instance in `_HANDLERS`; use `get_handler(type)`. Handlers implement the
  `ChannelHandler` protocol (`base.py`) and live in `handlers.py` (SOAP security-header swaps for
  Sabre/Amadeus/Travelport, header-key injection for NDC, placeholder substitution for Farelogix,
  structural login swap for Travelfusion). WSSE/SOAP helpers are in `wsse.py`. **Adding a channel =
  new `ChannelType` enum value + a handler + a `_HANDLERS` entry + golden tests** — see the
  `channel-implementation` skill.

- **`pii/` — the crypto + redaction engine.** `codec.py` (the `ENC_...` token format), `crypto.py`
  (keyring, HKDF, AES-256-CTR / AES-SIV), `engine.py` (select rules → locate nodes → encrypt/decrypt),
  `rules.py` + `rules_loader.py` (rule model + startup fetch/fallback), `smaz.py` (compress-if-smaller),
  `xml_ops.py` (**the hardened lxml parser factory — the only allowed way to parse XML**).

- **`observability/`** — Loguru JSON logging + OTel metrics (`metrics.py` defines the custom counters).

## Code style / behavior
- Full type hints; `mypy` strict and `pylint` must pass; `ruff` lint + format (line length 120).
- pydantic v2 for all config/structured data; JSON Schema is generated from models, never hand-written.
- Async I/O via `httpx.AsyncClient`; never block the event loop.
- XML only via the hardened lxml parser factory in `xml_ops.py` (no entities/DTD/network, size/depth
  limits). Never call `etree.fromstring` directly; never use `xmltodict` or text find-and-replace on
  bodies. Credential swaps and redaction are **structural** (parse → locate node → edit → re-serialize).
- Logging: Loguru JSON. Log `x-wenrix-trace-id`; never log bodies, PII, keys, or credentials.
- Keep pipeline stages small and independently testable.

## Security (hard constraints)
- Field crypto: AES-256-CTR, HKDF `K_enc`, keyring by 1-byte epoch; smaz-compress before encrypt
  (compress-if-smaller, flagged); token `ENC_ + base64url(control ‖ 96-bit IV ‖ ciphertext)`.
  Confidentiality-only in v1; do not drop IV below 96-bit; keep the format versioned.
- Keys come from the mounted Secret/env; never hard-coded, logged, or committed. The Helm Secret is
  create-if-absent; never regenerate keys on upgrade.
- Operation is parsed from the body, never trusted from a header. Constant-time secret comparison.
- On any crypto/rule/XML error, return the defined error response (`proxy/errors.py`, contract in
  `docs/PROJECT.md` §10); never forward partially processed PII. Whole-value token that won't decrypt
  → 502; an embedded `ENC_`-lookalike in free text is left untouched.

## Testing
Layers `tests/unit|integration|e2e` (+ `tests/deployment` for Helm/CI-workflow assertions); e2e uses
local mock channels (`deployment/mock_channel.py`) and stays fast. Golden tests use sanitized fixtures
in `tests/fixtures/`. Coverage gate is 85% (`just cov`). Required suites live in `openspec/specs/`.

## Git & review
Conventional Commits; short-lived branches; no direct pushes to `master`; PRs pass all required checks.
Primary review skill: **thermo-nuclear-code-quality-review**
(`npx skills add https://github.com/cursor/plugins --skill thermo-nuclear-code-quality-review`).
Run it on every non-trivial PR.

## Repo-local skills
`channel-implementation` (route, parser, structural swap, tests + PII rule authoring) already exists —
extend it, don't fork it. Author others with `skill-creator` as needed.

## Guardrails (do NOT)
- Log/persist PII, keys, or credentials.
- Forward Wenrix/forwarding/hop-by-hop headers or a `Server` header to a channel.
- Use `xmltodict`, unhardened XML parsing, regex find-and-replace on bodies, or text credential swap.
- Add retries, periodic rule polling, or regenerate the PII master key on `helm upgrade`.
- Introduce slow tests or real network calls in the suite.
- Break `WP_*` backward compatibility without an OpenSpec change and a migration note.
