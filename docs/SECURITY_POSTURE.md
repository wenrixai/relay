# Wenrix Channel Relay — Security Posture

**Audience:** customer / third-party security review.
**Scope:** the Wenrix Channel Relay (v2) service — source code, cryptography, configuration,
CI/CD and supply chain, container image, and Kubernetes / AWS deployment artifacts in this
repository.
**Status:** this document is a factual summary of controls present in the repository. Cross-references
point at the authoritative sources (`docs/PROJECT.md`, `SECURITY.md`, `.github/workflows/`, and the
`deployment/` tree) so every claim can be verified against code.

> This is a working draft intended to be enhanced/reformatted before external distribution.

---

## 1. What the service is (context for the threat model)

The relay is a **transparent, privacy-first HTTP/1.1 intermediary** placed in front of travel
distribution channels (Sabre, Amadeus, Travelport, Travelfusion, Farelogix, BA/LA NDC). Two design
properties drive the security model:

1. **Transparency** — the downstream channel must not be able to detect that Wenrix is in the path.
   All Wenrix/forwarding/hop-by-hop headers and the `Server` header are stripped; requests reach the
   channel de-anonymized (plaintext) with channel credentials swapped in.
2. **Field-level PII confidentiality** — on the response path the relay encrypts (redacts) traveler
   PII into self-describing `ENC_` tokens; on the request path it decrypts (de-anonymizes) them.
   Credential swap and PII are **opt-in per channel**; a zero-config channel is a straight
   pass-through.

The relay is **stateless** and **stores no persistent customer data** — no traveler PII or channel
payloads are written to disk or a database. It scales horizontally behind a load balancer.

---

## 2. Threat model (summary)

Full statement: `SECURITY.md` and `docs/PROJECT.md` §8–§10.

**Assets:** traveler PII carried in relayed XML; channel credentials for the connected channels.

**Adversaries:** an honest-but-curious surrounding platform (may observe relayed content but does not
actively attack it) and passive observers (parties that can read relayed XML in transit or at rest in
intermediate systems).

**Design version:** v1 is **confidentiality-only**. Transport integrity is provided by TLS; the relay
does not add cryptographic integrity to individual PII fields in the default mode.

**Explicitly out of scope for v1 (stated, not hidden):**

- Active token tampering / per-field cryptographic integrity in the default (AES-CTR) mode. AES-256-CTR
  provides confidentiality, not authentication. (The optional deterministic mode uses AES-SIV, which
  *is* authenticated — see §3.)

---

## 3. Cryptography & PII protection

Implementation: `src/channel_relay/pii/` (`crypto.py`, `codec.py`, `engine.py`, `smaz.py`, `xml_ops.py`).

### 3.1 Field encryption

- **Cipher:** AES-256-CTR (default mode), confidentiality-only in v1.
- **Token format:** `ENC_ + base64url_nopad(control_byte ‖ 96-bit IV ‖ ciphertext)`. The control byte
  carries a 4-bit key epoch, a "compressed" flag, a "deterministic" flag, and 2 reserved-zero bits
  (version headroom). `codec.py`.
- **IV:** 12 random bytes (96-bit) per encryption, generated with `os.urandom`; the IV is unique per
  `(key, field)` and random IVs prevent ciphertext-equality correlation. Contractually never reduced
  below 96 bits.
- **Compression:** smaz "compress-if-smaller" applied before encryption and flagged in the control byte;
  never expands the payload.

### 3.2 Deterministic mode (opt-in, authenticated)

- Optional per-rule **AES-256-SIV** (RFC 5297, no nonce). Same plaintext + same key epoch yields the
  same token, so a consuming system can compare redacted values by equality. This equality is a
  deliberate, documented, bounded leak enabled only for PII types the caller genuinely correlates.
- The 16-byte SIV synthetic IV doubles as an **authentication tag**, so deterministic tokens are
  additionally tamper-evident.

### 3.3 Key management

- **Master keys** live in an epoch-indexed keyring `{epoch: base64(32 bytes)}`, epochs 0–15. Master
  keys are **never used directly** as cipher keys.
- **Key derivation:** per-epoch `K_enc` and `K_siv` are derived via **HKDF-SHA256** with distinct
  domain-separation info strings (`wenrix-pii-enc-v1`, `wenrix-pii-siv-v1`). `crypto.py`.
- **Rotation:** via the 1-byte key epoch. A new epoch's key is added; new data encrypts under the new
  epoch; existing tokens stay decryptable under their original epoch until retired. No re-encryption
  event, no orphaned tokens.
- **Provisioning (Kubernetes):** the master-key Secret is **create-if-absent** and is
  **never regenerated on `helm upgrade`** (`helm.sh/resource-policy: keep` + a `lookup` guard). The
  keyring is mounted read-only and referenced by `RELAY_PII_KEYRING_FILE`. See §7.
- **Provisioning (AWS):** master key stored in AWS Secrets Manager with a 30-day recovery window and a
  `Retain` deletion/update-replace policy so tokens are never orphaned. See §8.
- **Validation:** keyring parsing rejects malformed JSON, empty keyrings, out-of-range/non-integer
  epochs, wrong key length (must decode to exactly 32 bytes), bad base64, or a missing active epoch.
  All error messages reference epoch numbers only — **never key material**.
- **Exposure surface:** only the epoch **ids** and the active epoch are ever exposed (e.g. via
  `/admin/flare`); raw key bytes are never returned outside internal crypto calls, logged, or committed.

### 3.4 Fail-closed crypto/PII behavior

The relay never forwards partially processed PII. On any crypto/rule/XML error it returns the defined
error response (§6) and drops the body.

- Redaction and de-anonymization wrap the entire pass; any unexpected error becomes
  `RedactionError` / `DeanonymizationError` and the caller returns **HTTP 502**. Error strings carry
  **only the exception type name** — never field values, tokens, or keys. `engine.py`.
- Token decryption fails closed on: missing `ENC_` prefix, malformed base64, truncated payload,
  **reserved control bits set (unsupported future version)**, unknown key epoch, SIV authentication
  failure (`InvalidTag` → "token authentication failed"), failed decompression, or non-UTF-8 output.
  `codec.py`.
- **Shape-dependent failure semantics:** a value that is *exactly* one `ENC_` token that will not
  decrypt → 502 (fail closed). An `ENC_`-lookalike span *embedded* in free text that will not decrypt
  is left untouched, because free text may legitimately contain such a string.

### 3.5 Structural-only edits (no text munging)

Credential swaps and PII redaction are **structural**: parse → locate node by XPath → edit → re-serialize.
Reference rules that scrub a name out of a free-text remark escape the collected value as a literal
(`re.escape`, never a caller-supplied regex) with optional word-boundary fencing. No regex
find-and-replace on raw bodies, no `xmltodict`.

---

## 4. XML parser hardening

The only permitted XML entry point is the hardened lxml factory in `src/channel_relay/pii/xml_ops.py`.
Ad-hoc `etree.fromstring` calls elsewhere are prohibited (enforced by review + the single sanctioned
call site).

Controls (`xml_ops.py`):

- `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `dtd_validation=False`,
  `huge_tree=False`.
- **DOCTYPE/DTD rejected outright** after parse (XXE, external-entity, and billion-laughs /
  entity-expansion protection).
- A custom resolver **raises on every external entity/DTD lookup** (belt-and-braces alongside
  `no_network`).
- **Resource limits:** max document bytes (default 8 MiB, shared with the body-inspection cap), max
  element depth (default 100), max node count (default 100,000).
- **Mapping to the error contract:** oversize → **HTTP 413**; DOCTYPE/DTD, depth, or node-count
  violations and malformed XML → **HTTP 502**. Parse-error kinds are surfaced as the
  `xml_parse_errors_total{kind}` metric label.
- **Unknown/undeclared namespace prefix in a rule path** → treated as a no-match for that rule (warning
  metric), never a crash.

Test coverage includes XXE / DTD / entity-expansion / oversize / malformed cases
(`tests/unit/test_pii_xml_ops.py`).

---

## 5. Authentication, authorization & transparency

### 5.1 Client authentication (`middleware/auth.py`)

- **HTTP Basic auth** is the default (v1 compatibility). **mTLS is opt-in**: the relay validates the
  client against the Wenrix certificate baked into the image; the **Wenrix private key never resides in
  the relay** (the relay cannot impersonate the Wenrix client).
- **Constant-time comparison:** credential checks use `hmac.compare_digest` for both username and
  password (both always evaluated) — no timing side channel.
- **Fail-closed startup:** if Basic auth is *enabled* but credentials are not configured, the process
  **refuses to boot**. Serving the data plane open is only possible when Basic auth is *explicitly*
  disabled.
- **Admin route is always fail-closed:** `/admin/flare` requires valid credentials even when data-plane
  auth is disabled.

### 5.2 Operation authorization

- Per-channel allow-list (`authorization.allowed_operations`) enforced **before** credential injection
  and before the upstream call.
- The **operation is always parsed from the request body, never trusted from a header** (unspoofable).
- A body that cannot be parsed / is not XML when authorization applies → **fail closed (403 denied)**.
- Blocked operation → **HTTP 401/403** with a fixed, PII-free detail.

### 5.3 Transparency / header hygiene (`middleware/header_hygiene.py`)

- **Hop-by-hop headers** (RFC 7230) stripped in both directions: `Connection`, `Keep-Alive`,
  `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`, plus
  any header named in the inbound `Connection` header.
- **Request path additionally strips** forwarding/identity headers (`X-Forwarded-For/-Host/-Proto`,
  `X-Real-IP`, `Forwarded`, `Via`), all `x-wenrix-*`, and all `proxy-*`; rewrites `Host` to the channel
  host (SNI set accordingly). The relay never *adds* `Via`/`Forwarded`/`X-Forwarded-*`.
- **Response path strips** hop-by-hop headers plus `Server` (recomputes `Content-Length`, drops
  `Content-Encoding` the relay changed).
- **`Server` header disabled** at the server level (`server_header=False`); asserted absent in tests
  (`tests/e2e/test_transparency.py`).

---

## 6. Error handling contract (fail-closed by design)

Source: `src/channel_relay/proxy/errors.py`; contract in `docs/PROJECT.md` §10.

- All relay-originated errors omit the `Server` header and carry an `X-Wenrix-Error: <reason>` header.
- **502 JSON** `{error, reason, detail, trace_id}` for internal / PII / credential-swap / XML failures.
  `detail` is human-readable and contains **no PII**. `reason` enum:
  `internal_error`, `pii_redaction_failed`, `pii_deanonymization_failed`, `xml_parse_error`,
  `credential_swap_failed`, `operation_not_allowed`, `unsupported_content_type`.
- **504** (text/html, v1 compat) on upstream timeout, `X-Wenrix-Error: upstream_timeout`.
- **401/403** on blocked operation; **413** on oversize body requiring inspection; **415/502** when a
  body requiring structured inspection is not XML/SOAP.

---

## 7. Network / forwarding policy

- **No request-level retries.** Once a request has reached the upstream it fails fast with a defined
  error — the calling client owns request-level retry policy. The only exception is a **pre-send
  connection-attempt retry** (`RELAY_UPSTREAM_CONNECT_RETRIES`, default 2): a failed TCP/TLS connect
  before any request bytes are sent, which can never duplicate an upstream side effect. `forwarder.py`,
  `settings.py`. (This prevents accidental double-processing of e.g. a ticketing request.)
- **No periodic polling.** PII redaction rules load **once at startup** (fetched from the Wenrix rules
  API if configured, otherwise a baked fallback bundle in the image); incompatible `schema_version` is
  rejected. `rules_loader.py`.
- **Upstream TLS:** verifying by default. A per-channel `tls.insecure_skip_verify` opt-out exists; when
  set it uses a *separate* non-verifying httpx client only for that channel, and every such channel is
  **logged loudly with a warning at startup**. Default channels always verify. `main.py`,
  `forwarder.py`.
- **Body inspection cap:** `RELAY_MAX_INSPECT_BYTES` = 8 MiB; oversize bodies requiring inspection →
  413.
- **Per-channel timeouts:** default connect 30s / read 120s, configurable per channel.

---

## 8. Secret handling (summary)

None of the following are logged or committed to the repository:

| Secret | Storage | Notes |
|---|---|---|
| PII master key (keyring) | K8s Secret (create-if-absent) / AWS Secrets Manager | Never regenerated on upgrade; retained on delete/uninstall so tokens are never orphaned; mounted read-only / injected via `valueFrom` |
| Basic-auth credentials | K8s Secret (`secretKeyRef`) / AWS Secrets Manager | Never in values/ConfigMap/env plaintext; template/plan errors if enabled without credentials |
| Channel credentials | Runtime config | Swapped structurally; never logged |
| Wenrix mTLS cert | Public cert baked into image | Private key never present in the relay |

Secrets are read from mounted files / injected env, **never from the channel JSON config**
(`settings.py`). The rendered ConfigMap contains channel definitions only ("Secrets are NEVER rendered
here").

---

## 9. Logging & observability (no sensitive data)

- **Structured JSON logs** via Loguru to stderr; stdlib/uvicorn logging is intercepted into one format.
- **Explicit guarantee:** "Bodies, PII, keys, and credentials are never logged." Call sites pass
  metadata only (channel name, content kind, redaction/decryption *counts*) — never values.
- **`backtrace=False, diagnose=False`** on the Loguru sink — prevents local variables/values from being
  dumped into tracebacks (a deliberate leak-prevention control).
- **Access log:** one JSON line per request with hostname, channel, method, path, status, latency,
  and `x-wenrix-trace-id` only.
- **`/admin/flare`** returns redacted operational diagnostics only: channel name/type/host, *sanitized*
  `proxy_pass` (userinfo/query/fragment stripped), booleans for swap/PII/auth enablement, credential
  **key names and counts (never values)**, rules version, key epoch **ids** (never key material), and
  readiness reasons. Protected by fail-closed admin auth.
- **Metrics:** in-process OpenTelemetry with OTLP export (push). Custom counters/gauges for redaction,
  de-anonymization, blocked operations, upstream timeouts, XML parse errors, and rules version.

---

## 10. Container image (`Dockerfile`)

- **Multi-stage Alpine** build (`uv` → `builder` → `runtime`). No compiler/toolchain in the final
  stage; the runtime stage copies only the built virtualenv.
- **Base images digest-pinned** by SHA256 (`ghcr.io/astral-sh/uv:0.11.28@sha256:…`,
  `python:3.14-alpine@sha256:…`), so a repointed upstream tag cannot silently change the image;
  Dependabot's docker ecosystem keeps the pins fresh.
- **Reproducible deps:** `uv sync --frozen --no-dev` against a committed `uv.lock`; dev dependencies
  excluded from the image; C/H source files deleted from the venv after build.
- **Non-root:** runs as numeric `USER 100:101`.
- **Hardening env:** `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `UV_PYTHON_DOWNLOADS=never`.
- **Healthcheck:** `/readiness` (30s interval, 3s timeout, 3 retries).

> `Dockerfile.mockserver` is a **test-only** stdlib mock channel used by compose/CI smoke tests. It is
> non-root but its base image is not digest-pinned and it has no healthcheck — acceptable because it is
> never a production artifact and is excluded from the deployment build context.

---

## 11. Kubernetes / Helm hardening (`deployment/helm/chart/`)

Chart is documented as "secure-by-default"; `kubeVersion: ">=1.25.0-0"`.

**Pod security context:** `runAsNonRoot: true`, `runAsUser: 100`, `runAsGroup: 101`, `fsGroup: 101`,
`seccompProfile.type: RuntimeDefault`.

**Container security context:** `runAsNonRoot: true`, `runAsUser: 100`,
`allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities.drop: [ALL]`.
Read-only root FS is made workable with a writable `emptyDir` at `/tmp`.

**Service account:** `automountServiceAccountToken: false` (pod spec and SA).

**Secrets:**

- PII keyring Secret is **create-if-absent** via a `lookup` guard: an existing Secret is reused; only a
  first install generates a fresh 32-byte master key. Annotated `helm.sh/resource-policy: keep` so it
  survives `helm uninstall`. Mounted read-only at `/etc/wenrix/keys`.
- Basic-auth credentials sourced only from a K8s Secret via `secretKeyRef`; `basicAuth.secretName` is a
  **required** value when Basic auth is enabled (hard template error otherwise).
- ConfigMap renders channel definitions only — no secrets.

**Availability:** 2 replicas by default; HPA (min 2 / max 10, CPU target 70%); PodDisruptionBudget
`minAvailable: 1`; liveness `/liveness`, readiness `/readiness`.

**Resource guarantees:** requests == limits (`cpu: 1000m`, `memory: 512Mi`) → Guaranteed QoS.

**Network segmentation:** the chart intentionally **ships no NetworkPolicy** (documented in
`NOTES.txt`); segmentation is delegated to cluster/cloud controls (security groups, customer-managed
`NetworkPolicy`, or service-mesh policy). Service is `ClusterIP` (not externally exposed by the chart).

---

## 12. AWS deployment (Terraform & CloudFormation)

Both `deployment/terraform/` and `deployment/cloudformation/wenrix-relay.yaml` describe the same
posture: **ECS Fargate behind an HTTPS-only ALB**.

- **TLS:** HTTPS listener on 443 with `ELBSecurityPolicy-TLS13-1-2-2021-06` (TLS 1.2/1.3) and an ACM
  certificate. **No plaintext HTTP:80 listener.** ALB `drop_invalid_header_fields = true`.
- **Ingress control:** ALB security group allows **443 only from a customer-supplied CIDR**
  (validation forbids an empty list; docs stress "never `0.0.0.0/0`"). The task security group accepts
  traffic **only from the ALB security group**, not from CIDRs.
- **Network placement:** tasks run in **private subnets** with `assign_public_ip = false` /
  `AssignPublicIp: DISABLED`; egress via NAT.
- **Task hardening:** `User "100"`, `readonlyRootFilesystem = true`, writable `/tmp` volume, graceful
  drain (`stopTimeout 120`), deployment circuit breaker + rollback, health-check grace period,
  Container Insights enabled.
- **Secrets:** PII keyring and Basic-auth credentials in **AWS Secrets Manager**, injected via
  `secrets`/`valueFrom` (ARN, not plaintext env). PII keyring has a 30-day recovery window and a
  `Retain` policy. Plan/deploy fails if Basic auth is enabled without both credentials. Sensitive
  parameters are `NoEcho` / marked `sensitive`.
- **IAM (least privilege):** the execution role adds an inline policy scoped to
  `secretsmanager:GetSecretValue` on **only this relay's specific secret ARNs**. The **task role has no
  attached policies** — the app makes no AWS API calls at runtime.
- **Logging:** CloudWatch `awslogs`, 30-day retention; CloudWatch alarms on ALB 5xx and unhealthy hosts.

> Note: `relay_config_json` / `RELAY_CONFIG_JSON` is passed as a plain environment variable and written
> to `/tmp/relay.json` at startup; it carries **channel configuration only, no secrets** (secrets are
> Secrets-Manager-injected as above).

---

## 13. CI/CD & supply-chain security (`.github/workflows/`)

All workflows default to **least-privilege `permissions: contents: read`**; elevated scopes are granted
per-job only.

### 13.1 CI (`ci.yml`)

On every push to `main`/`master` and every PR: change detection → `pre-commit` (full suite,
`--all-files`) → **pytest** (`-n auto --timeout=60 --cov=src --cov-fail-under=85`, i.e. parallel,
60s per-test timeout, **hard 85% coverage floor** with branch coverage) → **build image + `/readiness`
smoke test**. Image is pushed to GHCR only on push to `master` (job-scoped `packages: write`).

### 13.2 Security scanners (`security.yml`) — gating on PRs, plus weekly schedule

| Scanner | Tool | Config |
|---|---|---|
| SAST | GitHub **CodeQL** (`codeql-action@v4`, Python) | PR + weekly |
| Secrets scanning | **gitleaks** v8.21.2 | `--redact`, full history |
| Dependency vuln scan | **pip-audit** (via `uvx`) | against the frozen lockfile export |
| Container image scan | **Trivy** (`trivy-action@v0.36.0`) | `CRITICAL,HIGH`, `ignore-unfixed`, **`exit-code: 1`** (fails build on fixable findings) |

### 13.3 Release / supply chain (`release.yml`, on `v*` tags)

- Builds and pushes the versioned image to GHCR + OCI Helm chart.
- **SBOM** generated with **syft** (`anchore/sbom-action`), SPDX-JSON, attached to the GitHub Release.
- **Image signing** with **cosign keyless** (OIDC `id-token: write`) — **opt-in**, gated behind
  `vars.COSIGN_ENABLED == 'true'`.
- Changelog generated from git history; chart version bumped and pushed as an OCI artifact.

### 13.4 Pre-commit (`.pre-commit-config.yaml`) — same gates enforced locally

`check-json/yaml/toml`, `check-added-large-files`, `no-commit-to-branch` (blocks direct commits to
`main`), `pyupgrade`, **ruff** (lint + format), **gitleaks** v8.21.2, **actionlint** (workflow lint),
**hadolint** (Dockerfile lint), **mypy `strict=true`**, and **pylint**. CI runs the full suite via the
`quality` job.

### 13.5 Dependency management & code quality

- **Dependabot** (`dependabot.yml`) — weekly updates for `uv` (Python), `github-actions`, and `docker`
  ecosystems. Auto-merge (`dependabot-auto-merge.yml`) applies to **minor/patch only**; **major
  updates require manual review**.
- **Type safety:** mypy strict across `src`; **`filterwarnings = ["error"]`** (warnings are build
  errors); pytest `--fail-slow=500ms` performance gate; no slow tests / no real network in the suite.
- **Branch protection** (documented in `.github/BRANCH_PROTECTION.md`): PR + ≥1 approval + CODEOWNERS
  review; required status checks (`pre-commit`, `pytest`, image smoke, CodeQL, gitleaks, dependency
  audit, Trivy); linear history; dismiss stale approvals; no direct/force pushes to `master`.
- **PR template** includes a Definition-of-Done checklist with an explicit
  "No secrets/PII logged; header transparency preserved" item and a Security/transparency section.
- **CODEOWNERS:** `* @wenrix`.

---

## 14. Vulnerability disclosure & supported versions

From `SECURITY.md`:

- **Report privately to `security@wenrix.com`.** Do not open public issues/PRs for vulnerabilities.
- **Acknowledgement target:** within 3 business days. **Coordinated disclosure** up to 90 days from
  acknowledgement.
- **Supported versions:** the current minor and one prior minor receive security fixes (semver).

---

## 15. Known limitations / items to disclose proactively

Called out honestly so reviewers do not have to discover them:

- **v1 is confidentiality-only** in the default AES-CTR mode: no per-field cryptographic integrity
  against an active tamperer. The optional deterministic (AES-SIV) mode is authenticated. Transport
  integrity relies on TLS. (By design — see §2.)
- **SLSA build provenance is disabled** (`provenance: false`) on both the CI push and release image
  builds.
- **cosign image signing is opt-in** (`vars.COSIGN_ENABLED`) and does not run unless enabled.
- **GitHub Actions are pinned by version tag, not immutable commit SHA** (base container images *are*
  digest-pinned).
- **Branch protection is enforced in GitHub repo settings** (documented in the repo but not verifiable
  from repository contents alone).
- **No in-cluster NetworkPolicy** is shipped with the Helm chart — network segmentation is delegated to
  cluster/cloud controls (by design; AWS templates provide security-group segmentation).
- **Prometheus scrape / ServiceMonitor is inert** — the app is OTLP-push only today.
- **`Dockerfile.mockserver`** (test-only) uses an unpinned base image and has no healthcheck.
- **Terraform ALB `enable_deletion_protection = false`.**

---

## 16. Source references

| Area | Path |
|---|---|
| Security policy & threat model | `SECURITY.md` (root; `docs/SECURITY.md` points to it) |
| Full security design & decisions | `docs/PROJECT.md` (§8–§14, §17 locked decisions) |
| Cryptography / PII engine | `src/channel_relay/pii/` |
| XML hardening | `src/channel_relay/pii/xml_ops.py` |
| Auth / header hygiene / errors | `src/channel_relay/middleware/`, `src/channel_relay/proxy/errors.py` |
| Forward pipeline | `src/channel_relay/proxy/forwarder.py` |
| Startup fail-closed validation | `src/channel_relay/main.py` |
| Container image | `Dockerfile`, `.dockerignore` |
| Kubernetes / Helm | `deployment/helm/chart/` |
| AWS IaC | `deployment/terraform/`, `deployment/cloudformation/` |
| CI/CD & scanners | `.github/workflows/`, `.pre-commit-config.yaml`, `.github/dependabot.yml` |
| Engineering process / review | `CONTRIBUTING.md` |
