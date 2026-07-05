# Proposal: slice-5-hardened-deploy

## Why

Slices 1–3 deliver a safe, channel-aware relay but nothing yet packages it for production. Slice 5
makes the relay deployable and releasable: a hardened Helm chart, create-if-absent PII key
provisioning that survives upgrades, a tagged release pipeline, and a repeatable load/perf harness.

## What Changes

- Add a secure-by-default Helm chart under `deployment/helm/chart/` (§13.5): non-root, read-only
  root filesystem, dropped capabilities, seccomp `RuntimeDefault`, resource requests/limits,
  default-deny NetworkPolicy with an egress allow-list, HPA, PDB, probes to `/liveness` and
  `/readiness`, and a flagged ServiceMonitor.
- Provision the PII master-key Secret create-if-absent so `helm upgrade` never regenerates it
  (§13.2, §8.3, D4); all pods mount the same Secret file wired to `RELAY_PII_KEYRING_FILE`; document
  epoch rotation.
- Add `.github/workflows/release.yml` (§14): on tag `v*`, build and push the Alpine image to GHCR,
  generate an SBOM (syft), optionally cosign-sign, publish a GitHub Release with a Conventional
  Commits changelog, and bump the Helm chart `appVersion`. Document `RELEASE_CHECKLIST.md`.
- Add a k6 load/perf harness (§13.4) covering pass-through, credential-swap, PII-redaction, and
  redaction+de-anonymization round-trip scenarios across a 2KB/32KB/256KB payload matrix, published
  as a non-gating CI artifact.

## Impact

- Deployment: fills the empty `deployment/helm/chart/`; adds `perf/`, `release.yml`, and an optional
  perf workflow.
- Config: no new runtime config; the chart wires existing `RELAY_*` env and mounts existing Secrets.
- Security: keys are created once and never regenerated on upgrade; secrets are mounted, never placed
  in ConfigMaps or logs; NetworkPolicy restricts egress to channels/telemetry/DNS only.
- Metrics gap: the app is OTLP-push only, so the ServiceMonitor ships flag-default-off and a
  Prometheus scrape endpoint is called out as follow-up work (not built in this slice).
- Docs: `openspec/specs/` cross-references epoch rotation; `RELEASE_CHECKLIST.md` added.
