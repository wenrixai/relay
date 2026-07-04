## Context

Slice 1 builds the secure request/response pipeline (PROJECT.md §3.1) on the existing FastAPI
scaffold. Later slices bolt PII redaction, credential swap, and per-channel parsers onto the same
pipeline, so the stage boundaries chosen here must stay small and independently testable.

## Goals / Non-Goals

**Goals:**
- One channel relays end-to-end: auth → header hygiene → route → content → forward → hygiene →
  telemetry.
- Full header-hygiene and error contracts, correct enough to not need rework in later slices.
- Shippable: Alpine image, compose, CI, security automation.

**Non-Goals:**
- PII redaction / de-anonymization, credential swap, operation parsing, authorization (Slices 2–4).
- WP_* legacy synthesis beyond a loader hook (T4.3).
- mTLS, external authz, bundled otelcol (later phases).

## Decisions

- **Pipeline shape**: implement stages as small functions/helpers under `middleware/` invoked from the
  `/channel/{name}/{path}` route handler, not as ASGI middleware. This keeps each stage unit-testable
  in isolation and avoids ordering coupling with FastAPI's middleware stack. Auth is a FastAPI
  dependency scoped to `/channel/*` and `/admin/*`; probes stay dependency-free.
- **httpx client lifecycle**: a single `httpx.AsyncClient` created in the app `lifespan`, stored on
  `app.state`, closed on shutdown. Per-request `httpx.Timeout` from channel config; no transport-level
  retries (`transport=httpx.AsyncHTTPTransport(retries=0)` semantics — never add a retry loop).
- **Config load**: `lifespan` loads + validates config once; validation failure raises to abort
  startup non-zero. Readiness derives reasons from `app.state`.
- **Header hygiene**: a single canonical drop-set + dynamic `Connection`-listed tokens, applied on
  both directions. `Host` rewritten from channel host; SNI follows via the httpx URL host.
- **Errors**: central helpers in `proxy/errors.py` build the exact 504/502/413 shapes; `server_header
  =False` at uvicorn plus an assertion-in-tests guarantees no `Server`.
- **Metrics**: OTel `MeterProvider` with a `PeriodicExportingMetricReader` → OTLP; tests use an
  `InMemoryMetricReader` to assert increments without export.
- **Auth compare**: stdlib `hmac.compare_digest` on decoded basic-auth pairs; prefer no bcrypt dep
  unless htpasswd bcrypt hashes are required (defer to a follow-up if so).

## Risks / Trade-offs

- Streaming vs buffering: Slice 1 needs no body inspection, so bodies stream through; the inspectable
  cap (413) only applies once inspection is enabled. Guard the cap now so later slices inherit it.
- Handler-orchestrated pipeline (vs ASGI middleware) means the ordering lives in the route; documented
  here and mirrored from §3.1 to prevent drift.
- OTLP default endpoint (Wenrix) must be overridable and failure-tolerant so telemetry never crashes
  the relay.
