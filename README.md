# Wenrix Channel Relay (v2)

A privacy-first, transparent Python/FastAPI relay for travel channels. It provides structural
credential swap, PII redaction, and first-class observability while staying invisible to the
channel.

## Documentation
- **[openspec/specs/](openspec/specs/)** — canonical specification set (scope, architecture, security).
- **[openspec/changes/](openspec/changes/)** — change proposals, task lists, and archived deltas.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — workflow, Definition of Done, TDD, OpenSpec.

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
`RELAY_RULES_API_URL` at startup, baked fallback otherwise). See
`openspec/specs/relay-configuration/spec.md` and `openspec/specs/redaction-engine/spec.md`.

Body inspection is supported for XML/SOAP only (including gzip-encoded XML). JSON, MTOM/multipart,
deflate, and unknown content can pass through opaquely only when no configured stage needs to inspect
them; otherwise the relay fails closed rather than forwarding unprocessed sensitive content.

## Layout
```
src/channel_relay/   application package (main, config, middleware, channels, proxy, pii, observability)
tests/               unit | integration | e2e | fixtures | mocks
openspec/            spec-driven change workflow (specs/, changes/)
```
See `openspec/specs/` for the full target layout.
