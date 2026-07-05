# Agent Operating Rules — Wenrix Channel Relay (v2)

Agent/developer operating rules for this repository. This file is about **how to work**, not what to
build. Canonical requirements live elsewhere; read them first:

- **`openspec/specs/`** — product, security, architecture, and configuration requirements
  (source of truth).
- **`CONTRIBUTING.md`** — full workflow: Definition of Done, TDD, OpenSpec loop + exemptions, PR rules.

When code and `openspec/specs/` disagree, the spec wins: propose a change, do not drift.

## Golden rules
1. **Spec-driven + TDD.** Non-trivial work goes through the OpenSpec loop (details in
   `CONTRIBUTING.md`); write the failing test first. Exemptions (scaffold, typo, test-only, internal
   refactor) still need tests + green CI.
2. **No slow tests.** Every test finishes under the configured `pytest-timeout`. Mock the network.
3. **No retries.** Upstream calls fail fast; never add retry loops (the client owns retries).
4. **Never weaken crypto or leak secrets** (see Security below).
5. **Stay transparent.** The channel must never see Wenrix/forwarding/hop-by-hop headers or a
   `Server` header, and must receive de-anonymized (plaintext) requests.

## Commands
```bash
just ci            # full local pipeline (mirrors CI): sync + lint + fmt-check + types + pylint + test
just test-fast     # fast subset (excludes e2e)
just run           # uvicorn channel_relay.main:app --reload
just up            # docker compose (relay + mock channels)
uv add <pkg>       # add a dependency (never pip); keep uv.lock committed
uv run pytest      # tests
pre-commit run --all-files
```

## Code style / behavior
- Full type hints; `mypy` strict and `pylint` must pass; `ruff` lint + format.
- pydantic v2 for all config/structured data; JSON Schema is generated from models, never hand-written.
- Async I/O via `httpx.AsyncClient`; never block the event loop.
- XML only via the hardened lxml parser factory in `xml_ops.py` (no entities/DTD/network, size/depth
  limits). Never call `etree.fromstring` directly; never use `xmltodict` or text find-and-replace on
  bodies. Credential swaps and redaction are structural.
- Logging: Loguru JSON. Log `x-wenrix-trace-id`; never log bodies, PII, keys, or credentials.
- Keep middleware stages small and independently testable.

## Security (hard constraints)
- Field crypto: AES-256-CTR, HKDF `K_enc`, keyring by 1-byte epoch; smaz-compress before encrypt
  (compress-if-smaller, flagged); token `ENC_ + base64url(control ‖ 96-bit IV ‖ ciphertext)`.
  Confidentiality-only in v1; do not drop IV below 96-bit; keep the format versioned.
- Keys come from the mounted Secret/env; never hard-coded, logged, or committed. The Helm Secret is
  create-if-absent; never regenerate keys on upgrade.
- Operation is parsed from the body, never trusted from a header. Constant-time secret comparison.
- On any crypto/rule/XML error, return the defined error response from `openspec/specs/`; never forward
  partially processed PII.

## Testing
Layers `tests/unit|integration|e2e`; e2e uses local mock channels and stays fast. Required suites and
coverage gate are in the canonical spec set under `openspec/specs/`. Golden tests use sanitized
fixtures in `tests/fixtures/`.

## Git & review
Conventional Commits; short-lived branches; no direct pushes to `main`; PRs pass all required checks.
Primary review skill: **thermo-nuclear-code-quality-review**
(`npx skills add https://github.com/cursor/plugins --skill thermo-nuclear-code-quality-review`).
Run it on every non-trivial PR.

## Repo-local skills to author
Use `skill-creator` for: `channel-implementation` (route, parser, structural swap, tests),
`pii-rule-authoring` (rule schema, XPath/JSONPath + namespace conventions, review checklist),
`openspec-change` (this repo's propose → implement → archive loop).

## Guardrails (do NOT)
- Log/persist PII, keys, or credentials.
- Forward Wenrix/forwarding/hop-by-hop headers or a `Server` header to a channel.
- Use `xmltodict`, unhardened XML parsing, regex find-and-replace on bodies, or text credential swap.
- Add retries, periodic rule polling, or regenerate the PII master key on `helm upgrade`.
- Introduce slow tests or real network calls in the suite.
- Break `WP_*` backward compatibility without an OpenSpec change and a migration note.
