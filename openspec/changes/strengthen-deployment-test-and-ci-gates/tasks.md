# Tasks — strengthen deployment tests and CI gates

## 1. Helm key-reuse behavioral test (#11)

- [ ] 1.1 Add a kind/k3d-backed test: `helm install` → `helm upgrade` → assert the PII master-key Secret value is unchanged. Gate to a manual/nightly workflow (not the fast suite).
- [ ] 1.2 Keep the existing static `lookup` assertion as a cheap smoke; document that the behavioral test is the real guarantee.

## 2. CI gate coverage (#12)

- [ ] 2.1 Add `Dockerfile*` and `deployment/**` to the `test` job path filter, OR make `image`/`push-image` `needs: test` with a success condition (not `!= 'failure'`).
- [ ] 2.2 Add a regression assertion in `tests/deployment/` (workflow-lint style) that image/push cannot run on a skipped test job.

## 3. Supply-chain + image hygiene (LOW)

- [ ] 3.1 Pin `Dockerfile.mockserver` base by digest.
- [ ] 3.2 Decide build-provenance/cosign: enable `provenance: mode=max` (and/or default cosign) or document why off in `release.yml`.
- [ ] 3.3 Document the `HEALTHCHECK` `/readiness` choice (or switch to `/liveness` for plain `docker run`).
- [ ] 3.4 Document the custom-metrics-adapter prerequisite for `autoscaling.targetRequestsPerSecond`.

## 4. Verify

- [ ] 4.1 `openspec validate strengthen-deployment-test-and-ci-gates --strict`.
- [ ] 4.2 Fast suite unaffected/green; nightly workflow runs the kind test.
