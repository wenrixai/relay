# Remove the Helm NetworkPolicy; harden ECS deployment paths

## Why

A deployment review found the chart's NetworkPolicy renders an **allow-all** ingress rule by
default: with `ingressFromCIDRs: []`, the emitted rule has an empty `from:`, which the Kubernetes
API defines as "match all sources" — the opposite of the default-deny the template's comments,
NOTES.txt, and the spec claim. Rather than redesign it now, the NetworkPolicy is removed and network
segmentation is delegated to the customer's cluster/cloud controls (the primary customer deploys on
AWS ECS, where security groups fill this role and no NetworkPolicy equivalent exists).

The same review found both ECS IaC paths crash-loop out of the box (basic auth enabled with no
credential wiring) and miss standard production settings (deployment circuit breaker, stop timeout,
ALB idle timeout above the app's 120s read timeout, container health check).

## What Changes

- Helm: delete `templates/networkpolicy.yaml` and all `networkPolicy.*` values (including the
  `config.telemetry.otlpHost/otlpPort` values that existed solely for its egress rule); scrub
  NOTES.txt/README/docs claims. Chart README states TLS and network segmentation are expected at
  the ingress/cluster layer.
- Helm: fail-fast `required` guard when `basicAuth.enabled` and `basicAuth.secretName` is empty;
  remove the inert `tls.*` values/mount (the app cannot terminate TLS); HPA requests-per-second
  metric off by default (no scrape surface exists); correct the PII-keyring `lookup` documentation
  (RBAC + GitOps regeneration caveat).
- Terraform + CloudFormation: source basic-auth credentials from Secrets Manager and inject via the
  ECS `secrets` block; mark the channel-config JSON input `sensitive`/`NoEcho` (its plain-env
  delivery is an accepted design choice); add deployment circuit breaker, `stopTimeout`, health
  check grace period, explicit deregistration delay, ALB `idle_timeout` 130s, container health
  check (CFN), optional GHCR pull credentials and rules-API URL (TF), CloudWatch alarms (TF), and
  remove the hardcoded Application Auto Scaling service-linked-role ARN (CFN; breaks fresh
  accounts).
- Docs: new manual-ECS deployment guide; CloudFormation path mentioned in the configuration guide;
  OTLP examples gain explicit schemes; `relay.example.json` expanded.

## Capabilities

### Modified Capabilities
- `deployment-ci`: Helm hardening requirement no longer includes a NetworkPolicy; AWS hardening
  requirement gains basic-auth-from-Secrets-Manager and deploy-safety (circuit breaker) behavior.

## Impact

- `deployment/helm/chart/` (templates, values, README, NOTES), `tests/deployment/test_helm_chart.py`,
  `justfile` (`helm-test` flags).
- `deployment/terraform/`, `deployment/cloudformation/`.
- `docs/ECS_MANUAL_DEPLOYMENT.md` (new), `docs/PROXY_CONFIGURATION_GUIDE.md`, `docs/PROJECT.md`,
  `deployment/relay.example.json`, `Dockerfile` (base-image digest pins).
