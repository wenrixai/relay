# Tasks: slice-5-hardened-deploy

## 1. Spec

- [x] 1.1 Add OpenSpec delta for deployment-ci (Helm hardening, key provisioning, release flow,
      perf harness); `openspec validate --strict`.

## 2. Helm chart hardening (T5.1)

- [x] 2.1 TDD red: `helm lint` + `helm template` assertions (securityContext, probes,
      NetworkPolicy egress, no plaintext secrets in ConfigMap).
- [x] 2.2 Author `Chart.yaml`, `values.yaml`, `.helmignore`, and hardened templates
      (deployment, service, configmap, hpa, pdb, networkpolicy, servicemonitor, serviceaccount,
      helpers, NOTES).
- [x] 2.3 Add `just helm-test` recipe; templates pass lint + assertions.

## 3. Key provisioning (T5.2)

- [x] 3.1 TDD red: template assertions that the master-key Secret is created-if-absent (lookup
      guard) and mounted at the keyring file path; upgrade path emits no fresh key.
- [x] 3.2 Implement create-if-absent Secret + mount wired to `RELAY_PII_KEYRING_FILE`.
- [x] 3.3 Document epoch rotation in chart README/values and cross-ref `openspec/specs/`.

## 4. Release flow (T5.3)

- [x] 4.1 Add `.github/workflows/release.yml` (tag `v*`: GHCR build/push, SBOM, optional cosign,
      GitHub Release + changelog, Helm appVersion bump), least-privilege permissions.
- [x] 4.2 Add `RELEASE_CHECKLIST.md`.

## 5. Load/perf harness (T5.4)

- [x] 5.1 Add k6 script(s) under `perf/` with four scenarios and the payload matrix; ramped VUs;
      p50/p95/p99 + error-rate thresholds.
- [x] 5.2 Extend the mock channel with injectable upstream latency.
- [x] 5.3 Add perf workflow/job publishing `summary.json` as a non-gating artifact; `just perf`.

## 6. Close-out

- [x] 6.1 Collapse duplicate `justfile`/`Justfile` (git tracks only `justfile`; no action needed).
- [x] 6.2 Run `just ci`, pre-commit; lint/type/pylint/test/coverage green.
- [ ] 6.3 Archive OpenSpec change after validation and implementation.
