## 1. Helm

- [x] 1.1 Delete `templates/networkpolicy.yaml`; remove `networkPolicy.*` and
      `config.telemetry.otlpHost/otlpPort` values from `values.yaml`/`values-test.yaml`; scrub
      NOTES.txt, chart README, and `justfile helm-test` flags; update
      `tests/deployment/test_helm_chart.py` (drop netpol test, add `test_no_networkpolicy_rendered`).
- [x] 1.2 `required` guard: `basicAuth.enabled` with empty `secretName` fails render with an
      actionable message; helm tests render with a secretName and assert the failure case.
- [x] 1.3 Remove inert `tls.*` values and volume/mount; README notes TLS terminates at ingress/LB.
- [x] 1.4 `autoscaling.targetRequestsPerSecond: 0` default with rationale comment.
- [x] 1.5 Fix stale PII-keyring comment (lookup template, not hook Job); README documents RBAC and
      GitOps (`helm template`) regeneration caveat and the `piiKeyring.secretName` escape hatch.

## 2. Terraform

- [x] 2.1 `basic_auth_user`/`basic_auth_pass` sensitive vars → Secrets Manager secret → container
      `secrets` block; execution-role read policy extended; enabled-implies-credentials check.
- [x] 2.2 `relay_config_json` marked `sensitive`; tfvars.example comment corrected.
- [x] 2.3 Service: deployment circuit breaker, `health_check_grace_period_seconds`; container:
      `stopTimeout = 120`; target group: explicit `deregistration_delay`; ALB: `idle_timeout = 130`.
- [x] 2.4 Optional `rules_api_url` env, optional `repositoryCredentials` (GHCR), CloudWatch alarms
      (ALB 5xx, unhealthy hosts) with optional SNS topic; task-role intent comment.
- [x] 2.5 `terraform fmt -check && terraform validate` green; README/tfvars.example updated.

## 3. CloudFormation

- [x] 3.1 `BasicAuthUser`/`BasicAuthPass` NoEcho params → Secrets Manager secret → container
      `Secrets`; execution-role policy extended.
- [x] 3.2 `RelayConfigJson` param `NoEcho: true`.
- [x] 3.3 DeploymentCircuitBreaker; container `StopTimeout` + `HealthCheck`; TG
      `DeregistrationDelay`; service `HealthCheckGracePeriodSeconds`; ALB idle timeout 130.
- [x] 3.4 Remove hardcoded ScalableTarget `RoleARN`.
- [x] 3.5 README: single-NAT caveat, new parameters; `cfn-lint` green.

## 4. Docker & Docs

- [x] 4.1 Digest-pin base images in `Dockerfile` (real digests via
      `docker buildx imagetools inspect`).
- [x] 4.2 New `docs/ECS_MANUAL_DEPLOYMENT.md` (AWS CLI primary, console notes; no credential-swap
      content).
- [x] 4.3 `docs/PROXY_CONFIGURATION_GUIDE.md`: CloudFormation mention, OTLP scheme fixes, link to
      the manual guide, Helm table updates.
- [x] 4.4 Expand `deployment/relay.example.json`; update `docs/PROJECT.md` NetworkPolicy claim.

## 5. Verification

- [x] 5.1 `just ci` and `just helm-test` green; terraform validate; cfn-lint.
