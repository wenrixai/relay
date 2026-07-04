## Why

The relay has scaffolding (T1.1–T1.3) but does not yet relay any traffic. Slice 1 delivers the first
shippable, safe transparent relay: one channel end-to-end with header hygiene, basic auth, config,
observability basics, health, an Alpine image, and CI — with **no PII redaction or credential swap
yet** (deferred to Slices 2–3). This establishes the secure request/response pipeline every later
slice builds on.

## What Changes

- Pydantic-first configuration with a **generated** JSON Schema; invalid config aborts startup.
- App lifespan that loads config on startup; `/readiness` reports reasons and returns 503 when
  not-ready; `/liveness` stays trivial. Loguru JSON logging that never logs bodies/PII/keys.
- Routing `/channel/{name}/{path}` → resolve channel config → forward via `httpx` with per-channel
  connect/read timeouts and **no retries**; zero-config channels pass through untouched.
- Full HTTP header hygiene (§9.1): strip hop-by-hop, forwarding/identity, `x-wenrix-*`, and `Proxy-*`
  headers toward the channel; rewrite `Host`+SNI; never emit `Server`/`Via`/`Forwarded`.
- Content handling: transparent pass-through for non-XML/unknown; gzip decode/re-encode only when
  inspection is required; chunked supported; inspectable-body cap → 413; classify + log content type.
- Error contract (§10): 504 `text/html` on upstream timeout, 502 JSON on internal errors, 413 on
  oversize, each with `X-Wenrix-Error` and no `Server`.
- HTTP basic auth (default, toggleable) on served routes with constant-time comparison; probes stay
  open.
- Observability: in-process OTel metrics + OTLP export, access log, `channels_configured` and
  `upstream_timeouts_total` metrics.
- Multi-stage Alpine image (non-root, healthcheck), docker-compose with a mock channel, CI workflow,
  and security automation (Dependabot, CodeQL, gitleaks, dependency audit, Trivy, CODEOWNERS, PR
  template).

## Capabilities

### New Capabilities
- `relay-configuration`: pydantic config models, generated JSON Schema, loader, startup validation.
- `health-and-logging`: liveness/readiness probes with reasons, lifespan config load, JSON logging.
- `transparent-relay`: channel routing, httpx forwarding with per-channel timeouts, content handling.
- `header-hygiene`: full hop-by-hop / forwarding / identity header contract, Host+SNI rewrite.
- `error-contract`: 504 / 502 / 413 error shapes with `X-Wenrix-Error` and no `Server`.
- `client-authentication`: default HTTP basic auth, constant-time compare, toggle, open probes.
- `observability`: OTel metrics + OTLP export, access log, custom metrics.
- `deployment-ci`: Alpine image, compose, CI pipeline, security automation.

### Modified Capabilities
<!-- None: this is the first behavioral slice; no existing specs change. -->

## Impact

- Code: `src/channel_relay/{main,settings,health}.py`, new modules under `config/`, `middleware/`,
  `proxy/`, `observability/`.
- Dependencies (via `uv add`): `opentelemetry-sdk`, `opentelemetry-exporter-otlp`.
- Infra: `Dockerfile`, `Dockerfile.mockserver`, `docker-compose.yml`, `.github/workflows/*`,
  `.github/{dependabot.yml,CODEOWNERS,PULL_REQUEST_TEMPLATE.md}`.
- Config surface: `RELAY_*` env vars and JSON channel config per the relay-configuration spec.
