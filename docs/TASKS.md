# Wenrix Channel Relay (v2) — OpenSpec task lists

User stories organized as **vertical slices**: each slice delivers a working, shippable relay with
more capability than the last, rather than building all horizontal layers before anything runs. See
`PROJECT.md` for design, `CONTRIBUTING.md` for the workflow/DoD/OpenSpec/TDD rules, `the relay-configuration spec` for
config.

## Definition of Done (every story)
See `CONTRIBUTING.md`. In short: OpenSpec change (unless exempt) · TDD · ruff + ruff format + mypy
strict + pylint clean · tests green · no slow tests · coverage gate met · docs/CONFIG updated ·
secrets/PII never logged · thermo-nuclear review on non-trivial PRs · Conventional Commits · CI green.

## Legend
Priority P0–P3. `Depends:` references story IDs. Slices are sequential; stories within a slice may
parallelize.

---

## Slice 1 — Walking skeleton: a safe transparent relay (MVP)
Goal: one channel relays end-to-end with header hygiene, basic auth, config, observability basics,
health, Alpine image, CI. No PII, no credential swap yet.

### T1.1 — Project scaffold + tooling (P0)
uv-managed FastAPI project (Python 3.13); layout per PROJECT.md §3.2; ruff + mypy (strict) + pylint
configured; typing required. `uv run` boots an empty app.

### T1.2 — Pre-commit setup (P0) — Depends: T1.1
`.pre-commit-config.yaml`: ruff, ruff-format, mypy, pylint (fast subset), gitleaks, check-json/yaml,
end-of-file-fixer, trailing-whitespace, no-commit-to-branch (main). `pre-commit install` documented;
CI runs `pre-commit run --all-files`.

### T1.3 — justfile developer shortcuts (P0) — Depends: T1.1
`just ci` runs the full local pipeline (sync + lint + fmt-check + types + pylint + test) mirroring
CI; plus `just test-fast` (no e2e), `lint`, `fmt`, `types`, `run`, `up`, `precommit`.

### T1.4 — Config: pydantic models + generated JSON Schema (P0) — Depends: T1.1
Pydantic v2 config models; JSON Schema **generated** from models (no hand-written schema.json);
invalid config aborts startup with a clear error. Only `name`+`type` required; per-type host default.

### T1.5 — Health + app skeleton + structured logging (P0) — Depends: T1.1
`/liveness`, `/readiness` with reasons; Loguru JSON logging wired (never logs bodies/PII/keys);
app factory + lifespan.

### T1.6 — Routing + transparent pass-through, one channel (P0) — Depends: T1.4
`/channel/<name>/...` resolves to config; forward via httpx with per-channel connect/read timeouts;
**no retries**; host/proxy_pass override; zero-config channel passes through untouched.

### T1.7 — Header hygiene (full contract) (P0) — Depends: T1.6
Implement PROJECT.md §9.1: drop hop-by-hop headers (`Connection`, `Keep-Alive`, `TE`, `Trailer`,
`Transfer-Encoding`, `Upgrade`, `Proxy-*`, and Connection-listed) both directions; strip
`X-Forwarded-*`, `X-Real-IP`, `Forwarded`, `Via`, all `x-wenrix-*` toward the channel; do not add
`Via`/`Forwarded`; rewrite `Host` + SNI; disable `Server` (uvicorn `server_header=False`). Tests
assert a clean upstream request and no `Server` in responses.

### T1.8 — Content handling: gzip/chunked/non-XML pass-through (P0) — Depends: T1.6
Per PROJECT.md §5.4: transparent pass-through for non-XML/unknown; decode/re-encode gzip only when
body inspection is required; support chunked; enforce inspectable-body cap → 413. (JSON NDC and
MTOM parsing are later; classify + log only.)

### T1.9 — Error contract (P0) — Depends: T1.6
Implement PROJECT.md §10: 504 text/html + `X-Wenrix-Error: upstream_timeout` on channel timeout;
502 JSON `{error,reason,detail,trace_id}` + `X-Wenrix-Error` for internal errors; 413 for oversize.
Exact status/headers/body covered by tests.

### T1.10 — Basic auth (default) (P0) — Depends: T1.5
htpasswd-style basic auth on all served routes; config-driven on/off; constant-time compare.

### T1.11 — Observability basics (P0) — Depends: T1.5
In-process OTel metrics + OTLP export (endpoint configurable, default Wenrix); OTel HTTP semconv
server+client metrics; access log with `hostname`, channel-endpoint, latency, `x-wenrix-trace-id`;
shared tags host/customer/version; `channels_configured`, `upstream_timeouts_total`.

### T1.12 — Alpine Dockerfile + compose + CI (P0) — Depends: T1.5
Multi-stage Alpine image (non-root, musllinux wheels for lxml/cryptography), healthcheck; compose
with a mock channel; `ci.yml` (uv sync → ruff → format check → mypy → pylint → pytest w/ timeout +
coverage → build image → `/readiness` smoke). Fail fast, no retries.

### T1.13 — Security automation (P0) — Depends: T1.12
Dependabot (pip/uv + actions, auto-merge on green), CodeQL, gitleaks, dependency audit, Trivy image
scan; branch protection + PR template + CODEOWNERS.

---

## Slice 2 — PII redaction core (one channel)
Goal: encrypt PII on responses and de-anonymize on requests for the Slice-1 channel.

### T2.1 — Crypto keyring (P0) — Depends: T1.1
AES-256-CTR + HKDF (`K_enc`); keyring indexed by 1-byte epoch; master key from Secret/env; negative
tests (wrong key/epoch).

### T2.2 — Token codec + smaz (P0) — Depends: T2.1
`ENC_ + base64url(control ‖ 96-bit IV ‖ ciphertext)`; smaz compress-if-smaller (flag in control);
round-trip + IV-uniqueness + "never larger than raw + fixed overhead" property tests.

### T2.3 — Hardened XML ops (P0) — Depends: T1.1
`xml_ops.py` hardened lxml parser factory (PROJECT.md §9.4): no entities/DTD/network, depth/size/
node limits, namespace-failure = no-match + metric, malformed → 502; XXE/billion-laughs/oversize
tests. All XML parsing goes through this factory.

### T2.4 — Rule model + loader (P0) — Depends: T1.4
Rule schema (`schema_version`, `rules_version`, rules[], `path_type` xpath|jsonpath); fetch on
startup + baked fallback; reject incompatible schema; no polling; `rule_version` metric.

### T2.5 — Redaction engine, response (P0) — Depends: T2.2, T2.3, T2.4
Select rules by channel+operation; XPath locate via hardened parser; skip ignored patterns;
encrypt/mask; structure-preserving re-serialize; off unless channel opts in; error → 502 JSON;
golden tests on fixtures.

### T2.6 — De-anonymization engine, request (P0) — Depends: T2.2
Envelope-driven `ENC_` scan → decode → epoch → key → CTR-decrypt → smaz-decompress → replace;
error → 502 JSON; e2e round-trip (encrypt on response, decrypt on later request).

### T2.7 — PII metrics (P1) — Depends: T2.5, T2.6
`pii_fields_redacted_total`, `pii_fields_decrypted_total`, `xml_parse_errors_total`.

---

## Slice 3 — All channels + credential swap
Goal: every supported channel with operation parsing and opt-in structural swap.

### T3.1 — Channel abstraction (P0) — Depends: T1.6
`base.py` protocol: `parse_operation`, `swap_request`, `swap_response`; `registry.py`; swap is a
no-op without configured credentials.

### T3.2 — Operation parsers from body (P0) — Depends: T3.1
Per-channel parser (SOAP action / root element / NDC type); never trusts headers; golden tests.

### T3.3–T3.9 — Per-channel swap (P1) — Depends: T3.1, T3.2
One story each: Travelfusion, BA NDC, LA NDC, Farelogix AA/LH/UA(+EK), Amadeus, Sabre, Travelport.
Structural swap per PROJECT.md §5.2 (never find-replace); runs only when configured; response login
removal where applicable; v1-parity tests on sanitized fixtures.

### T3.10 — Per-channel test fixtures (P0) — Depends: T3.2
`tests/fixtures/<channel>/`: sanitized real request+response (+JSON where relevant) with expected
swapped/redacted output; drives golden tests. Sanitization removes all real PII/credentials.

### T3.11 — Sabre/Amadeus response auth-field encryption (P1) — Depends: T2.5, T3.6/T3.8
Encrypt authentication fields in responses for Sabre and Amadeus (PROJECT.md §4.7).

---

## Slice 4 — Authorization, admin, config completeness
### T4.1 — Authorization: allowed_operations (P1) — Depends: T3.2
Per-channel `allowed_operations` with semver `version` match; block → 401 (exact schema §10.4);
`authorization_blocked_total`.

### T4.2 — /admin/status + CLI (P1) — Depends: T1.4, T2.4
Redacted status: config summary, active channels (type/host/swap-configured/pii-enabled),
`rules_version`, available key epochs (ids only), telemetry state, readiness reasons. No secrets/PII;
same auth as routes; redaction test.

### T4.3 — the relay-configuration spec + WP_* migration parity (P0) — Depends: T1.4
Complete `the relay-configuration spec` (env vars, JSON fields, precedence, defaults, examples, secret formats); legacy
loader synthesizes channels from every `WP_*`; parity test vs a v1 config sample; env vars marked
deprecated.

---

## Slice 5 — Hardened deployment, release, perf, docs
### T5.1 — Helm chart hardening (P1) — Depends: T1.12
Per PROJECT.md §13.5: securityContext (non-root, read-only rootfs, drop caps, seccomp), resource
requests/limits, NetworkPolicy (default-deny + egress allow-list to channels/telemetry/DNS), HPA,
PDB, ServiceMonitor (flagged), Secret mounts, probes → `/liveness` `/readiness`.

### T5.2 — Key provisioning in Helm (P1) — Depends: T2.1, T5.1
Master-key Secret **created-if-absent** (never regenerated on upgrade); all pods mount it; documented
epoch rotation.

### T5.3 — Release flow (GHA) (P1) — Depends: T1.12
`release.yml` on tag `v*`: derive semver, build+push Alpine image (GHCR), SBOM (syft), optional
cosign sign, GitHub Release + changelog (Conventional Commits), bump Helm chart appVersion. Document
in `RELEASE_CHECKLIST.md`.

### T5.4 — Load/perf harness (P2) — Depends: T2.5
Implement PROJECT.md §13.4: 50 rps/instance @ 1000m vCPU target; hardware baseline; payload matrix
(2KB/32KB/256KB); ramped concurrency with p50/p95/p99; scenarios pass-through / swap / redaction /
round-trip; fixed mock upstream latency; pass/fail thresholds; k6 or locust; results as CI artifact
(non-gating by default).

### T5.5 — Security & contribution docs wired (P1)
Ensure `SECURITY.md`, `CONTRIBUTING.md`, `.github/` templates, and the review skill
(`thermo-nuclear-code-quality-review`) are referenced from README; verify links.

### T5.6 — Documentation portal (P1) — Depends: T4.3
Main article + sub-articles (install/config incl. Helm/K8s + channel implementation; advanced
config; PII redaction explainer); deprecate old env vars.

---

## Slice 6 — Later capabilities (postponed by design)
### T6.1 — Advanced (external) authorization (P2) — Depends: T4.1
Forward to authz API; 200 → allow else 407 + `Proxy-Authenticate`; `strict` fails closed on timeout.

### T6.2 — Bundled otelcol (P2) — Depends: T1.11
otelcol as a second in-container process; app → localhost → Wenrix; collector failure never crashes
the relay; supervised lifecycle.

### T6.3 — Free-text anonymization (Presidio) (P3) — Depends: T2.5
`rule_type: free_text` via Presidio NER (optional FLAIR) behind a flag; spans encrypted with the codec.

### T6.4 — Optional pii_ref correlation (P3) — Depends: T2.1
`pii_ref = HMAC(K_ref, customer_id ‖ channel ‖ pnr_id ‖ passenger_id)[:12]`; off by default.

### T6.5 — JSON NDC + MTOM parsing (P3) — Depends: T2.5, O6
JSONPath rule support for JSON NDC channels; MTOM/multipart handling beyond opaque pass-through.

---

## Delivery order
Slice 1 → Slice 2 → Slice 3 → Slice 4 → Slice 5 → Slice 6.
Slice 1 alone is a shippable, safe transparent relay. Do not start Slice 2 until Slice 1 is green.
