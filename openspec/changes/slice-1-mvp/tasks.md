## 1. Configuration (T1.4)

- [ ] 1.1 Pydantic config models per the relay-configuration spec (`config/models.py`, `settings.py`)
- [ ] 1.2 Generated JSON Schema (`config/json_schema.py`)
- [ ] 1.3 Loader with startup-abort on invalid config (`config/loader.py`)
- [ ] 1.4 Tests: minimal channel defaults, invalid aborts, schema required fields, enum reject

## 2. Health + logging (T1.5)

- [ ] 2.1 Loguru JSON logging, no bodies/PII/keys (`observability/logging.py`)
- [ ] 2.2 App lifespan loads config; readiness reasons + 503 (`health.py`, `main.py`)
- [ ] 2.3 Tests: liveness 200, readiness reasons, log line JSON without body

## 3. Routing + forwarding (T1.6)

- [ ] 3.1 `/channel/{name}/{path}` resolve config, httpx forward, per-channel timeouts, no retries
- [ ] 3.2 Tests (mock transport): forward method/path/query/body, unknown → 404, timeout honored

## 4. Header hygiene (T1.7)

- [ ] 4.1 Strip hop-by-hop/forwarding/wenrix/proxy headers; rewrite Host+SNI; no Server/Via/Forwarded
- [ ] 4.2 Tests: clean upstream request, no Server on responses

## 5. Content handling (T1.8)

- [ ] 5.1 Transparent pass-through, gzip only when inspecting, chunked, cap → 413, classify+log
- [ ] 5.2 Tests: gzip byte-identical, oversize → 413, chunked relayed, classifier tags type

## 6. Error contract (T1.9)

- [ ] 6.1 504 timeout text/html, 502 JSON internal, 413 oversize, X-Wenrix-Error, no Server
- [ ] 6.2 Tests: exact status/headers/body; trace_id echo

## 7. Basic auth (T1.10)

- [ ] 7.1 Basic auth on served routes, constant-time compare, toggle, probes open
- [ ] 7.2 Tests: no/wrong/right creds, disabled flag, probes reachable

## 8. Observability (T1.11)

- [ ] 8.1 OTel metrics + OTLP export, access log fields, channels_configured, upstream_timeouts_total
- [ ] 8.2 Tests: metric increment via in-memory reader, access log fields, no PII

## 9. Deployment + CI (T1.12)

- [ ] 9.1 Multi-stage Alpine Dockerfile (non-root, healthcheck) + Dockerfile.mockserver
- [ ] 9.2 docker-compose.yml (relay + mock channel)
- [ ] 9.3 ci.yml pipeline (sync→lint→fmt→types→pylint→pytest→build→smoke)

## 10. Security automation (T1.13)

- [ ] 10.1 dependabot.yml, security.yml (CodeQL, gitleaks, dep audit, Trivy)
- [ ] 10.2 CODEOWNERS, PULL_REQUEST_TEMPLATE.md, branch-protection note

## 11. Close-out

- [ ] 11.1 `just ci` green, coverage ≥85%, pre-commit all hooks pass
- [ ] 11.2 Archive change into `openspec/specs/`
