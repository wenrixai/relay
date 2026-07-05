# Wenrix Channel Relay (v2)

A privacy-first, transparent Python/FastAPI relay for travel channels. It preserves v1
`WP_*` behaviour and adds structural credential swap, PII redaction, and first-class
observability — while staying invisible to the channel.

## Documentation
- **[docs/PROJECT.md](docs/PROJECT.md)** — canonical spec (scope, architecture, security).
- **[docs/the relay-configuration spec](docs/the relay-configuration spec)** — configuration reference and `WP_*` migration.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — workflow, Definition of Done, TDD, OpenSpec.
- **[docs/SECURITY.md](docs/SECURITY.md)** — threat model, disclosure, secret handling.

## Requirements
- Python 3.13 (pinned in `.python-version`)
- [uv](https://docs.astral.sh/uv/) (package manager — never pip)
- [just](https://github.com/casey/just) (task runner)
- [OpenSpec](https://github.com/Fission-AI/OpenSpec) CLI (change workflow)

## Getting started
```bash
uv sync                     # create the venv from uv.lock
uv run pre-commit install   # enable git hooks
just ci                     # full local pipeline (mirrors CI)
just run                    # run the relay locally (uvicorn --reload)
```

## Common commands
```bash
just              # list all recipes
just test-fast    # fast test subset (excludes e2e)
just cov          # tests with coverage gate
just lint / fmt / types / pylint
```

## PII redaction (opt-in)
Per channel, `pii.enabled: true` turns on response redaction and request de-anonymization:
PII fields in channel responses are replaced with self-describing `ENC_` tokens
(AES-256-CTR, epoch keyring) before Wenrix sees them, and tokens in later requests are
decrypted back to plaintext before reaching the channel. Requires a keyring
(`RELAY_PII_KEYRING` / `RELAY_PII_KEYRING_FILE`) and redaction rules (fetched from
`RELAY_RULES_API_URL` at startup, baked fallback otherwise). See `docs/PROJECT.md` §7-§8
and `docs/the relay-configuration spec`.

## Layout
```
src/channel_relay/   application package (main, config, middleware, channels, proxy, pii, observability)
tests/               unit | integration | e2e | fixtures | mocks
openspec/            spec-driven change workflow (specs/, changes/)
docs/                canonical specification and references
```
See `docs/PROJECT.md` §3.2 for the full target layout.
