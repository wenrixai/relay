# Wenrix Channel Relay (v2) — PROJECT.md

> Canonical engineering specification and single source of truth for scope, architecture, and
> product/security requirements.
> Companions: `openspec/changes/` (change proposals and task lists),
> `openspec/specs/relay-configuration/spec.md` (configuration requirements),
> `CONTRIBUTING.md` (workflow/DoD/TDD/OpenSpec), and `SECURITY.md` (disclosure/threat model).

---

## 1. Overview

### 1.1 Problem
The previous proxy used nginx + OpenResty/Lua text substitution for credential injection. It could
not support PII redaction, contextual structural credential handling, or first-class observability,
and its per-message text substitution was brittle.

### 1.2 Goal
A modern Python (FastAPI) relay that adds a privacy-first, zero-trust path where Wenrix never sees
traveler PII in readable form, structural credential swap, more
channels (Amadeus, Sabre, Travelport), and real observability/testability/Helm deployment.

### 1.3 Non-negotiable principles
- **Transparent relay**: the channel must never learn Wenrix is in the path (§9).
- **Zero-config channels**: any supported channel relays out of the box; credential swap and PII are
  opt-in (§5.1, §7).
- **Stateless** app instances (§12.6 covers upstream sessions); horizontally scalable.
- **No request-level retries** (§10.5): a request that reached the upstream fails fast with a
  defined error; only a pre-send connection attempt may retry.

### 1.4 Glossary
| Term | Meaning |
|------|---------|
| Relay / Proxy | This on-premise service (v2). |
| Channel | Upstream travel API (GDS, NDC, or XML API such as Travelfusion). |
| Client | The Wenrix optimization service that calls the relay. |
| Customer | The entity deploying the relay in their own infrastructure. |
| Operation | The channel action a message performs (e.g. `PNR_Retrieve`), parsed from the body. |
| PII token | An `ENC_...` value replacing a redacted field (§8.4). |

---

## 2. Tech stack

| Concern | Choice | Notes |
|---|---|---|
| Language | **Python 3.13** | `.python-version` pins it; typing required everywhere. |
| Framework | **FastAPI** / `uvicorn` | Middleware/mediator pipeline (§3). |
| HTTP client | **httpx** (async) | Per-channel connect/read timeouts; no request-level retries, connect-only retry allowed (§10.5). |
| Packaging | **uv** | `pyproject.toml` + `uv.lock`; `uv sync --frozen`. Never pip. |
| Models/config | **pydantic v2** + **pydantic-settings** | Primary validator; JSON Schema is **generated** from the models (§6.1). No hand-maintained `schema.json`. |
| XML | **lxml**, hardened parser (§9.4) | Namespace-aware XPath + structural edits. `xmltodict` not used. |
| Compression | **smaz** (antirez) | Compress PII plaintext before encryption (§8.4). |
| Crypto | **cryptography** (`hazmat`) | AES-256-CTR, HKDF (§8.3–8.4). |
| Logging | **Loguru** | Structured JSON; never logs PII/keys/bodies. |
| Telemetry | **OpenTelemetry SDK**; bundled **otelcol** (later phase) | MVP = in-process OTLP/metrics (§11). |
| Lint/format | **ruff** (lint + format) | |
| Types | **mypy** (strict) | Required type hints on all public code. |
| Lint (extra) | **pylint** | Complements ruff for design/smell checks. |
| Tests | **pytest** (+ `pytest-timeout`, `pytest-asyncio`) | No slow tests (§13.3). |
| Container | **Alpine** base | Small image; relies on musllinux wheels for lxml + cryptography (§13.1). |

---

## 3. Architecture

### 3.1 Request/response pipeline (middleware / mediator)
Ordered, independently testable stages.

```
Client (Wenrix)
   │ request
   ▼
[1]  Auth              basic-auth (default) / mTLS (opt-in)                    §9.2
[2]  Header hygiene    strip hop-by-hop + forwarding + Wenrix headers          §9.1
[3]  Route + resolve   /channel/<name>/... → channel config; Host rewrite      §5,§9.1
[4]  Content gate      handle gzip XML; classify XML vs unsupported/opaque     §5.4
[5]  Operation parse   parse operation from body (per-channel parser)          §5.3
[6]  Authorization     allow/block operation (semver); external authz (later)  §12
[7]  De-anonymize      replace ENC_ tokens with plaintext (request)            §8.6
[8]  Credential swap   inject/replace credentials (opt-in)                     §5.2
   │ forward (httpx, per-channel timeouts, no retries)
   ▼
Channel ── response ──►
[9]  Redact (PII)      encrypt PII fields per rules (response)                 §8.5
[10] Header hygiene    strip Server + hop-by-hop; Wenrix-facing diagnostics    §9.1,§10
[11] Telemetry         metrics, access log, trace-id                           §11
   │ response
   ▼
Client (Wenrix)
```
Redaction runs on the response path; de-anonymization on the request path. Credential swap and PII
are no-ops unless configured for that channel.

### 3.2 Repository layout
```
channel-relay/
├── pyproject.toml  uv.lock  .python-version  .pre-commit-config.yaml
├── ruff.toml       .pylintrc (or pyproject)  justfile
├── Dockerfile (Alpine)  docker-compose.yml  Dockerfile.mockserver
├── README.md  docs/PROJECT.md  CONTRIBUTING.md  SECURITY.md  LICENSE
├── openspec/                 # project.md + templates (TDD), specs/, changes/
├── src/channel_relay/
│   ├── main.py  settings.py  health.py  admin.py     # /admin/status (§12.7)
│   ├── config/    models.py  loader.py  json_schema.py  # schema generated
│   ├── middleware/ pipeline.py auth.py header_hygiene.py authorization.py
│   │               timeouts.py access_log.py telemetry.py content.py
│   ├── channels/  base.py registry.py travelfusion.py ba_ndc.py la_ndc.py
│   │               farelogix.py amadeus.py sabre.py travelport.py
│   ├── proxy/     forwarder.py errors.py                # error contract §10
│   ├── pii/       rules.py engine.py crypto.py codec.py xml_ops.py
│   └── observability/ logging.py metrics.py collector/
├── deployment/helm/chart/    # hardened (§13.5)
├── tests/  unit/ integration/ e2e/ fixtures/ mocks/ conftest.py
│           # fixtures/<channel>/ : sanitized request+response + expected swapped/redacted (§13.6)
└── .github/  workflows/{ci,security,release}.yml  dependabot.yml  CODEOWNERS
            PULL_REQUEST_TEMPLATE.md  ISSUE_TEMPLATE/  RELEASE_CHECKLIST.md
```

---

## 4. Functional requirements
1. Versioned JSON configuration; semver image tags (warn against `latest`).
2. Process settings from `RELAY_*` environment variables (§6).
3. Header hygiene toward the channel (§9.1).
4. Channels: Travelfusion, BA NDC, LA NDC, Farelogix AA/LH/UA (+EK), Amadeus/NDCx, Sabre, Travelport (§5).
5. Per-channel proxy-pass/host override.
6. **Structural** credential swap (parse → locate → edit), never text find-and-replace.
7. Encrypt authentication fields in responses for Sabre and Amadeus.

---

## 5. Channels & content

### 5.1 Config model (zero-config default)
Only `name` and `type` are required; `host` defaults per type. Credential swap runs only when
`credentials.enabled: true`; otherwise the request passes through untouched even if credential
fields are present. PII is off unless `pii.enabled: true`. Full reference in
`openspec/specs/relay-configuration/spec.md`.

### 5.2 Credential swap table (opt-in)
| Channel | Swap (only if `credentials.enabled: true`) |
|---|---|
| Travelfusion | Structural set of `CommandList/<op>/LoginId`, `/XmlLoginId` in request; strip login fields from response. |
| BA NDC | Add `Client-Key` header. |
| LA NDC | Add API key header. |
| Farelogix AA/LH/UA/EK | Add `Ocp-Apim-Subscription-Key`; substitute request-body placeholders (`#FLX_USERNAME#`, `#FLX_PASSWORD#`, `#FLX_AGENT#`, `#FLX_AGENT_USER#`, `#FLX_AGENT_PASSWORD#`) from config. |
| Amadeus / Sabre / Travelport | Replace the SOAP security header. |

### 5.3 Operation parsing
Always parsed **from the body** by a per-channel parser (SOAP action / root element / NDC message
type). Never trusts a client-supplied header (unspoofable). Drives rule selection (§8) and
authorization (§12).

### 5.4 Content handling (payload types)
Structured body inspection is XML/SOAP-only:
- **XML/SOAP** (Travelfusion, Farelogix, Amadeus, Sabre, Travelport): full parse/edit/redact path
  (§8), hardened parser (§9.4).
- **gzip XML**: decode when the relay must inspect the body, apply structural processing, then
  preserve the appropriate wire encoding toward the next hop.
- **chunked transfer-encoding**: supported; the relay buffers only as needed for inspection and
  streams otherwise. Enforce a max inspectable body size (§9.4); oversize → 413.
- **JSON, MTOM/multipart, deflate, and unknown content**: opaque pass-through only when no configured
  stage requires inspection. If request inspection is required, fail before forwarding with 415
  `unsupported_content_type`; if response inspection is required, return 502 with the same reason
  and none of the upstream body.

---

## 6. Configuration

### 6.1 Pydantic-first validation
Config is expressed as **pydantic models** (single source). JSON Schema is **generated** from the
models (`config/json_schema.py`) and used for external validation/publishing; there is no
hand-maintained `schema.json`. On invalid config, log the validation error and **abort startup**
(non-zero exit). Precedence, defaults, environment mapping, and secret formats are specified in
`openspec/specs/relay-configuration/spec.md`.

---

## 7. PII management
- Off by default; enabled per channel.
- Redaction on the **response**; de-anonymization on the **request** (NDC rebooking needs the real
  name).
- PII types: `person`, `dob`, `gender`, `nationality`, `passport_id`, `visa`, `phone`, `email`,
  `address`, `payment`, `frequent_flyer`. Not PII: PNR reference, ticket number, itinerary/fare.

---

## 8. PII redaction design

### 8.1 Rule format
```json
{ "schema_version": "1.0", "rules_version": "2026-07-01", "rules": [
  { "id": "amadeus.pnr_retrieve.person.001",
    "channel": "amadeus", "operation": "^PNR_Retrieve$",
    "path": "//ns:Traveler/ns:Name", "path_type": "xpath",
    "rule_type": "field", "pii_type": "person", "method": "encrypt",
    "ignored_content_patterns": ["^TMX"] } ] }
```
`path_type`: `xpath` (the only supported value). `method`: `encrypt` (default) | `mask`.
`rule_type`: `field` (default) | `reference`.

**`deterministic` (encrypt only, default `false`).** Random-IV `encrypt` yields a *different*
token per occurrence, so any caller logic comparing PII values by equality (matching a passenger
across responses, deduplicating names) breaks. Setting `"deterministic": true` switches that rule
to AES-SIV (§8.4): same plaintext + same key epoch → same token, preserving equality for the
caller. Authoring guidance: enable it only for pii_types the caller genuinely correlates by value
(coordinate with the consuming team — `person` is the expected first case); it deliberately
reveals equality patterns (the same passenger is recognizable across responses within an epoch),
an accepted, bounded leak. Rollout order matters: deploy relays that understand the flag
everywhere *before* flipping it in rules — older relays reject deterministic tokens fail-closed.
Within one response no flag is needed: the engine reuses the same token for every occurrence of
the same exact plaintext (per encryption mode) in a single redaction pass, including reference-rule
hits, so intra-response equality always holds.

A **reference** rule redacts occurrences of PII values that `field` rules already extracted this
same pass — the name that also appears inside a free-text remark (Amadeus/Sabre `RM`/`OSI`/`SSR`).
It declares `source_pii_types` (which extracted buckets to hunt), a bounded target `path` (the
free-text nodes to search — never document-wide), guards `min_match_len` (default 3) and
`word_boundary` (default true, case-insensitive), and a reversible `encrypt` action:
```json
{ "id": "amadeus.pnr_reply.remark.001", "rule_type": "reference",
  "channel": "amadeus", "operation": "^PNR_Reply",
  "path": "//ns:generalRemark/ns:remarkText", "path_type": "xpath",
  "source_pii_types": ["person"], "pii_type": "person", "method": "encrypt" }
```
Matching is literal (a collected value is a fixed string, escaped, never a regex) and structural
(edits the parsed node's text, never the raw body). Values live only for the one pass — no
persistence, no cross-request memory.

### 8.2 Matching flow
Detect channel from route; parse operation from body; select rules where `channel` matches and
`operation` regex matches; locate nodes by path; skip `ignored_content_patterns`; apply method;
re-serialize preserving structure/namespaces.

### 8.3 Keys
Master key per **key-epoch**; HKDF domain separation (`K_enc`; `K_siv` for deterministic §8.4;
`K_ref` only for optional §8.9).
Master key from a Helm **create-if-absent Secret** (§13.5) so restarts/upgrades never orphan tokens.
Rotation via the 1-byte epoch keyring: add a new epoch's key, retain prior epochs for decryption.

### 8.4 Token format (self-describing, transparent)
```
plaintext  = utf8(field_value)
comp       = smaz(plaintext)
payload    = comp if len(comp) < len(plaintext) else plaintext
control    = (key_epoch & 0x0F) | (compressed << 4) | (deterministic << 5)  # bits 6-7 reserved
# default mode (deterministic bit clear):
iv         = random 12 bytes (96-bit)
ciphertext = AES-256-CTR(K_enc[key_epoch], counter=iv||0x00000000, payload)
token      = "ENC_" + base64url_nopad(control || iv || ciphertext)
# deterministic mode (bit 5 set, opt-in per rule):
token      = "ENC_" + base64url_nopad(control || AES-256-SIV(K_siv[key_epoch], payload))
```
Regex `^ENC_([A-Za-z0-9_-]+)$`. Default mode: IV prepended in clear (CTR cannot encrypt its own
IV); unique per (key,field); random IV prevents ciphertext-equality correlation.
**Confidentiality-only in v1** (TLS provides transport integrity; threat model = a party *reading*
the XML, not tampering, per `SECURITY.md`). Deterministic mode (RFC 5297, no nonce): the 16-byte
synthetic IV doubles as an authentication tag, so those tokens are additionally
tamper-evident; equality across responses is the intended, documented leak (§8.1). Decrypt routes
on bit 5 — de-anonymization stays envelope-driven and mode-blind. Format is versioned via the
remaining reserved bits; an authenticated default mode can be added later without breaking it.
Size note: for short names the fixed 13-byte overhead dominates, so smaz gains are largest on longer
PII; IV length is tunable in `codec.py` (never below 96-bit).

### 8.5 / 8.6 Encrypt (response) / decrypt (request)
Encrypt: parse → select rules → per node compute payload/iv/ciphertext → replace with `ENC_...` →
re-serialize. Decrypt: scan values for the `ENC_` marker (envelope-driven, no rule needed) → decode
→ epoch → key → CTR-decrypt → smaz-decompress if flagged → replace. The scan matches each `ENC_`
token whether it is the whole value or **embedded** in free text (so remark-scrubbed names, §8.1
reference rules, round-trip). Shape decides failure semantics: a whole-value token that will not
decrypt → **502 JSON** (§10.3, fail closed); an embedded `ENC_`-lookalike span that will not
decrypt is left untouched (free text may legitimately contain one). Never forward partially
processed PII.

### 8.7 Free text
Two complementary mechanisms. **Reference rules** (§8.1, shipped) scrub free text by reusing values
that structured rules already extracted this pass — deterministic, no ML, bounded to declared remark
paths. A later, separate phase MAY add `rule_type: free_text` using Presidio NER (optional FLAIR)
behind a feature flag for PII the channel *originates* that no structured rule extracted; detected
spans encrypted with the same codec.

### 8.8 Rule delivery
Fetch latest versioned rules from the Wenrix rules API on startup; if unreachable, use the **baked
fallback bundle** in the image. **No periodic polling.** Reject incompatible `schema_version`.

### 8.9 Optional correlation (`pii_ref`) — later phase
Opt-in `pii_ref = HMAC(K_ref, customer_id ‖ channel ‖ pnr_id ‖ passenger_id)[:12]`. Off by default.

---

## 9. Security & transparency

### 9.1 Header handling (full contract)
The relay is an HTTP/1.1 intermediary and must handle headers correctly, not just strip a few names.
- **Hop-by-hop headers** (RFC 7230) are never forwarded in either direction: `Connection`,
  `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`,
  `Transfer-Encoding`, `Upgrade`, plus any header listed in the inbound `Connection` header.
- **Forwarding/identity headers** stripped before the channel: `X-Forwarded-For`, `X-Forwarded-Host`,
  `X-Forwarded-Proto`, `X-Real-IP`, `Forwarded`, `Via`, and all `x-wenrix-*`. The relay does **not**
  add `Via`/`Forwarded`/`X-Forwarded-*` (transparency: the channel must not detect an intermediary).
- **Host**: rewrite `Host` to the channel host (per channel config), with SNI set accordingly.
- **`Proxy-*`**: never forwarded to the channel (used only for the advanced-authz hop, §12.1).
- **Compression**: `Accept-Encoding`/`Content-Encoding` handled per §5.4; do not blindly forward a
  `Content-Encoding` the relay changed.
- **`Server` header**: disabled. Uvicorn/FastAPI emit `Server` by default; configure the server
  (`server_header=False`) and assert its absence in tests. Same for the `Date`-only minimal surface.
- **Diagnostic headers**: opt-in, default-off, Wenrix-facing only, never sent to the channel. The
  single exception is the timeout/error indicator on 502/504 (§10), which is Wenrix-facing (O1).

### 9.2 Client authentication
**HTTP basic auth is the default** (v1 compat). **mTLS is opt-in**: verify the client against the
Wenrix certificate baked into the image (Wenrix private key stays on Wenrix servers). Constant-time
credential comparison.

### 9.3 Dependency hygiene
Dependencies updated at least monthly; automated scanning in CI (§14). No persistent storage of
customer data.

### 9.4 XML parser hardening (mandatory)
lxml must be configured defensively for all untrusted XML:
- `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `dtd_validation=False`; reject
  DOCTYPE/DTD (XXE and external-entity protection; billion-laughs / entity-expansion protection).
- Disable/deny external entity resolution via a custom resolver that raises.
- **Limits**: max document bytes (inspectable-body cap, shared with §5.4), max element depth, max
  node/attribute count; exceed → reject with **413** (size) or **502** (structural).
- **Namespace failure**: unknown/undeclared namespace prefixes in a rule path → treat as a
  no-match for that rule and emit a warning metric; never crash.
- **Malformed XML**: parse failure on a body the relay must inspect → **502 JSON** (§10.3);
  passthrough-only channels are unaffected.
- Reuse a hardened parser factory in `xml_ops.py`; no ad-hoc `etree.fromstring` calls.

---

## 10. Error handling (contract)

### 10.1 Principles
Every error is one of the shapes below. Text/HTML is used only where v1 compatibility requires it;
new relay-originated errors use JSON. All error responses omit `Server`.

### 10.2 Upstream timeout — HTTP 504
`Content-Type: text/html` (v1 compat), body is a short HTML notice, plus header
`X-Wenrix-Error: upstream_timeout`. Emitted when a channel exceeds its connect/read timeout.

### 10.3 Relay/internal & PII errors — HTTP 502
`Content-Type: application/json`:
```json
{ "error": "bad_gateway", "reason": "pii_redaction_failed",
  "detail": "human-readable, no PII", "trace_id": "<x-wenrix-trace-id>" }
```
`reason` enum includes `internal_error`, `pii_redaction_failed`, `pii_deanonymization_failed`,
`xml_parse_error`, `credential_swap_failed`. Header `X-Wenrix-Error: <reason>`.

### 10.4 Authorization — 401 / 407
- Operation blocked by `allowed_operations` → **401** JSON `{ "error": "unauthorized",
  "reason": "operation_not_allowed", "operation": "<op>" }`.
- External authz deny/timeout (advanced, later) → **407 Proxy Authentication Required** with
  `Proxy-Authenticate: Basic realm="proxy.com"` (compat with proxy-auth semantics).
- Rationale for the split: 401 is a relay policy decision on the parsed operation; 407 mirrors the
  external proxy-authentication handshake the advanced feature emulates.

### 10.5 Retries and body limits
**No request-level retries** on upstream calls: once a request has been sent, failure (timeout,
reset, non-2xx) fails fast with a defined error — the calling client owns request-level retry
policy, not the relay. The shared httpx transport MAY retry a failed **connection attempt**
(`RELAY_UPSTREAM_CONNECT_RETRIES`, default 2) — connect refused/timeout before any request bytes
are sent — because no upstream side effect can have occurred yet; this can never cause a request to
be processed twice. Bodies exceeding the inspectable-size cap when inspection is required → **413**.

---

## 11. Observability
- **MVP**: structured JSON logs (Loguru); in-process OTel metrics + OTLP export; access log per
  channel endpoint with `hostname`, channel-endpoint name, latency (measured on response receipt),
  and `x-wenrix-trace-id`; OTel HTTP semconv server+client metrics; shared tags `host`, `customer`,
  `version`; per-signal enable/disable and endpoint override (default = Wenrix endpoint).
- **Later phase**: bundled **otelcol** process in the same container for buffering/compression; app
  → localhost → Wenrix. Collector failure must not crash the relay.
- Dashboard monitors each deployment; export a Prometheus/OTLP surface a `ServiceMonitor` can scrape
  (§13.5).

### 11.1 Custom metrics
| Name | Type | Description | Tags |
|---|---|---|---|
| `channels_configured` | gauge | Configured channels | `channel` |
| `pii_fields_redacted_total` | counter | Fields encrypted (response) | `channel`, `pii_type` |
| `pii_fields_decrypted_total` | counter | Tokens de-anonymized (request) | `channel` |
| `authorization_blocked_total` | counter | Operations blocked | `channel`, `operation` |
| `upstream_timeouts_total` | counter | 504s | `channel` |
| `xml_parse_errors_total` | counter | Hardening/parse rejects | `channel`, `kind` |
| `rule_version` | gauge/info | Loaded rules version | `rules_version` |

---

## 12. Authorization, sessions, admin

### 12.1 API authorization
Per-channel `authorization.enabled` plus `authorization.allowed_operations` with semver `version`
match; operation parsed from body; not-allowed → 401 (§10.4). Omitted `authorization.enabled`
defaults false, so configured rules are inert until explicitly enabled. **Advanced (external)
authorization is a later phase**: forward to an authz API; non-200 → 407; `strict` flag fails
closed on timeout.

### 12.6 Upstream stateful sessions (design decision)
The motivation mentions "stateful connections for Amadeus/Sabre." The relay app stays **stateless**;
sessions are handled without shared cross-instance state:
- **v1 model**: session/login/logout and token-refresh flows are **client-managed pass-through**.
  Wenrix performs the login and carries the session token on each request; the relay forwards it
  (after de-anonymizing any tokens) and does not hold session state. This keeps instances stateless
  and horizontally scalable behind any load balancer.
- **Optional later capability**: a **per-instance, in-memory** upstream session/token cache (never
  shared, never persisted) for channels that require the relay to hold a session, with a documented
  affinity requirement. This is out of MVP scope and must be proposed via OpenSpec.
- Client certificates for a channel (if required) are mounted per deployment and used by the httpx
  client; they are configuration, not runtime session state.
This item is flagged in §18 (O5) for confirmation of the v1 pass-through assumption.

### 12.7 Admin/status endpoint
A **redacted** `GET /admin/status` (and an equivalent CLI subcommand) returns operational state with
**no secrets/PII**: config summary, active channels (name/type/host, swap-configured bool,
pii-enabled bool), `rules_version`, available key epochs (ids only, never key material), telemetry
state (signals enabled + endpoints), and readiness reasons (why not-ready if applicable). Protected
by the same auth as other routes; safe to expose to operators.

---

## 13. Deployment & testing

### 13.1 Container
Multi-stage **Alpine** image, non-root, minimal. lxml and cryptography install from **musllinux**
wheels (no compiler in the final image); if a wheel is unavailable, add build deps only in the build
stage. App (+ otelcol in the later phase) with a healthcheck. Semver tags; production guidance
against `latest`.

### 13.2 Key provisioning (Helm)
Master key Secret **created-if-absent** (pre-install hook / lookup), never regenerated on
`helm upgrade`; all pods mount the same Secret; rotation via key epoch documented.

### 13.3 Testing
- pytest layers: `unit`, `integration`, `e2e` (against local mock channel servers).
- **No slow tests**: global `pytest-timeout` (e.g. 1s); CI fails on overrun. e2e stays fast via local
  mocks.
- Required suites: crypto round-trip + IV-uniqueness + "token never larger than raw + fixed
  overhead" property tests; codec; per-channel operation parsers; rule engine golden tests on
  sanitized fixtures (§13.6); XML hardening (XXE/DTD/entity-expansion/oversize/malformed) tests;
  header-hygiene tests (hop-by-hop, `Server` absent, no `Via`/`Forwarded` to channel); error-contract
  tests (exact status/headers/body); `/admin/flare` redaction test.
- Coverage gate (placeholder 85%; confirm — O2).

### 13.4 Load / performance methodology
Target: **50 requests/sec per instance at 1000m vCPU / defined memory**, with a repeatable harness.
Specify and record:
- **Hardware baseline**: 1000m vCPU, fixed memory (e.g. 512Mi) request/limit; note the runner class.
- **Payload matrix**: small (~2KB), medium (~32KB), large (~256KB) representative GDS/NDC messages.
- **Concurrency**: ramped virtual users (e.g. 1→64) to find the knee; report p50/p95/p99 latency and
  error rate at the target rps.
- **Scenarios**: (a) pure pass-through, (b) credential swap only, (c) PII redaction enabled,
  (d) redaction + de-anonymization round-trip. Report each separately (redaction has real cost).
- **Mock channel latency**: fixed injected upstream latency (e.g. 50ms) so relay overhead is
  isolated from network.
- **Pass/fail thresholds**: sustain ≥50 rps/instance at the p95 latency budget (define, e.g.
  ≤ upstream+50ms overhead) with error rate <0.1%, no memory growth over a soak window.
- Tool: `locust` or `k6` in a dedicated job; results published as a CI artifact (not gating by
  default).

### 13.5 Kubernetes / Helm hardening (chart requirements)
The chart must ship secure-by-default:
- **PodSecurityContext / container securityContext**: non-root UID, `runAsNonRoot: true`,
  `readOnlyRootFilesystem: true` (writable `emptyDir` only where needed, e.g. tmp/otelcol),
  `allowPrivilegeEscalation: false`, drop all capabilities, seccomp `RuntimeDefault`.
- **Resource requests/limits**: CPU/memory set (align with §13.4 baseline).
- **Network segmentation**: delegated to cluster/cloud controls (security groups, a
  customer-managed `NetworkPolicy`, service mesh policy) — the chart ships no `NetworkPolicy`.
- **HPA**: scale on CPU/RPS; **PDB**: minAvailable for rolling updates.
- **ServiceMonitor**: expose metrics for Prometheus scraping (guarded by a values flag).
- **Secret mounting**: PII key and TLS/basic-auth material mounted from Secrets (not env where
  avoidable); no secrets in ConfigMaps or logs.
- Probes wired to `/liveness` and `/readiness`.

### 13.6 Test fixtures (per channel)
Under `tests/fixtures/<channel>/`, ship **sanitized** real GDS/XML request+response pairs with the
**expected swapped and/or redacted output**. These drive golden
tests for parsers, credential swap, and redaction. Sanitization removes all real PII/credentials.

---

## 14. CI/CD (intent; exact steps live in `.github/workflows/*` and OpenSpec changes)
CI enforces, on every PR: `uv sync` → ruff lint → ruff format check → mypy strict → pylint → pytest
(with `pytest-timeout` + coverage gate) → Alpine image build → container smoke test (`/readiness`).
Security automation: Dependabot (auto-merge on green), CodeQL, gitleaks, dependency audit, Trivy
image scan. Release on tag: semver, changelog, image push, SBOM (syft), optional cosign, Helm chart
version bump. Branch protection with required checks + PR template + CODEOWNERS.

---

## 15. Documentation
Main article + sub-articles: install & configuration (incl. Helm/K8s + channel implementation),
advanced configuration, and PII redaction explainer. Document process and channel configuration in
`docs/PROXY_CONFIGURATION_GUIDE.md` and `openspec/specs/relay-configuration/spec.md`.

---

## 16. Development workflow
uv, ruff, mypy (strict), pylint, pre-commit; **OpenSpec drives non-trivial changes and TDD is
mandatory**. Full workflow, Definition of Done, and OpenSpec exemptions live in **`CONTRIBUTING.md`**
(single source; other files reference it). Conventional Commits; short-lived branches; PRs with
required checks. Primary review skill: `thermo-nuclear-code-quality-review`.

---

## 17. Locked decisions
| # | Decision |
|---|---|
| D1 | Field cipher: AES-256-CTR, confidentiality-only in v1 (TLS for integrity). |
| D2 | Self-describing token `ENC_ + base64url(control ‖ 96-bit IV ‖ ciphertext)`; IV in payload; nothing echoed. |
| D3 | smaz compress-if-smaller, flagged in `control` byte. |
| D4 | Key rotation via 1-byte epoch keyring; master key from Helm create-if-absent Secret. |
| D5 | lxml only, **hardened** (§9.4); `xmltodict` not used. |
| D6 | Operation always parsed from the body (unspoofable). |
| D7 | Rules: startup fetch + baked fallback; no periodic poll. |
| D8 | Client auth: basic-auth default, mTLS opt-in. |
| D9 | Telemetry: MVP in-process OTLP; bundled otelcol a later phase. |
| D10 | Zero-config channels: only `name`+`type` required; swap & PII opt-in. |
| D11 | Transparent to channel: full header hygiene (§9.1), no `Server`, no `Via`/`Forwarded`. |
| D12 | **No request-level retries** on upstream calls; only a pre-send connection-attempt retry is allowed (§10.5). |
| D13 | Config: pydantic-first; JSON Schema generated, not hand-written. |
| D14 | Container base: Alpine (musllinux wheels). |
| D15 | Tests/lint: ruff + mypy strict + pylint + required typing; no slow tests. |
| D16 | Upstream sessions: client-managed pass-through in v1; app stateless (§12.6). |
| D17 | Ship in vertical slices through OpenSpec changes; postpone advanced authz, `pii_ref`, Presidio, otelcol. |

## 18. Open items to confirm
- O1: The single Wenrix-facing timeout/error diagnostic header (§9.1, §10) vs the "no extra headers"
  goal (spec requires it).
- O2: Coverage gate % and per-test timeout threshold.
- O3: Wenrix rules-API contract (URL, auth, response shape) for §8.8.
- O4: Whether Farelogix `#FLX_*#` placeholders are guaranteed XML-embedded (structural) or may be
  raw-string (would need scoped, contextual substitution).
- O5: Confirm the v1 upstream-session model is client-managed pass-through (§12.6), i.e. no relay-held
  GDS/NDC sessions in v1.
