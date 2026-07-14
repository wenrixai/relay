# Strengthen deployment tests and CI gates

## Why

Several deployment/CI gaps mean the most safety-critical deployment behavior is asserted only weakly,
and some changes ship without the test gate running.

1. **Helm key-reuse guard is untested behaviorally.** `test_helm_chart.py` only regex-checks that
   `lookup "v1" "Secret"` appears in the template text; `helm lookup` returns empty under offline
   `helm template`, so "upgrade preserves the existing master key" — the single most safety-critical
   Helm behavior (D4, and the "PII key provisioning survives upgrade" requirement) — is never
   exercised. A refactor that breaks the guard would pass CI.

2. **CI `test` job is path-filtered.** A PR touching only `Dockerfile`, `deployment/**`, or workflow
   files skips `test`, and the `image` job treats a skipped `test` as pass-through — so a Dockerfile
   change can build and (on `master`) push to GHCR with **zero tests run** in that logic gate,
   including the `/readiness` smoke that is supposed to prove the image.

3. **Lesser infra gaps.** `Dockerfile.mockserver` uses an unpinned `python:3.14-alpine` (no digest),
   inconsistent with the main image's digest-pinning rationale; OCI build-provenance is disabled
   (`provenance: false`) and cosign signing is opt-in, so supply-chain attestation is off by default;
   the `HEALTHCHECK` targets `/readiness` (flaps unhealthy on transient not-ready under plain
   `docker run`); and `autoscaling.targetRequestsPerSecond` references a custom metric with no scrape
   surface by default.

## What Changes

- Add a kind/k3d-backed integration test (install → upgrade → assert the master-key Secret is
  unchanged), gated to a manual/nightly workflow so the fast suite stays fast — the create-if-absent
  guarantee is verified behaviorally, not by regex.
- Make the CI test gate cover deployment/Dockerfile/workflow changes: include those paths in the
  filter, or make `image`/`push-image` depend on `test` **succeeding** (not merely "not failed").
- Pin `Dockerfile.mockserver` by digest; make an explicit decision on build-provenance/cosign
  (enable `provenance: mode=max` or document why off); document the `HEALTHCHECK` choice; document the
  custom-metrics-adapter prerequisite for RPS autoscaling.

## Capabilities

### Modified Capabilities
- `deployment-ci`: the key-survives-upgrade guarantee is behaviorally tested; the CI gate cannot be
  bypassed by path-filtering for deployment/image changes.

## Impact

- `tests/deployment/`: kind/k3d upgrade test (manual/nightly).
- `.github/workflows/ci.yml`: path filter / job dependency fix; optional provenance toggle.
- `Dockerfile.mockserver`: digest pin.
- `deployment/helm/chart/values.yaml`, docs: autoscaling + healthcheck notes.
