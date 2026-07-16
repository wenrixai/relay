# wenrix-relay Helm chart

Hardened Kubernetes deployment for the Wenrix Channel Relay (PROJECT.md §13.5, §13.2).

## Install

```bash
kubectl create secret generic relay-basic-auth \
  --namespace wenrix \
  --from-literal=user=<USER> --from-literal=pass=<PASS>

helm install relay deployment/helm/chart \
  --namespace wenrix --create-namespace \
  --set image.tag=v0.1.0 \
  --set basicAuth.secretName=relay-basic-auth \
  --set config.telemetry.otlpEndpoint=http://otel-collector.telemetry:4317
```

Channels are set via `config.channels` (rendered into a ConfigMap as `/etc/wenrix/relay.json`).
Secrets are **never** placed in values or the ConfigMap.

## Security defaults (§13.5)

- Pod/container run as non-root (`runAsNonRoot`, numeric UID), `readOnlyRootFilesystem: true`
  (writable `/tmp` emptyDir only), `allowPrivilegeEscalation: false`, all capabilities dropped,
  seccomp `RuntimeDefault`.
- CPU/memory requests == limits at the perf baseline (1000m / 512Mi).
- Network segmentation is delegated to cluster/cloud controls (e.g. security groups, a
  customer-managed `NetworkPolicy`) — this chart does not ship one. An empty-`from:` NetworkPolicy
  ingress rule matches all sources, so a chart-managed default was removed rather than shipped
  effectively allow-all; apply your own policy alongside this chart if network segmentation is
  required.
- `HorizontalPodAutoscaler` (CPU; RPS scaling off by default — see Key values) and
  `PodDisruptionBudget`.
- Probes to `/liveness` and `/readiness`.
- `ServiceMonitor` is shipped **disabled** — the relay is OTLP-push only and has no Prometheus
  scrape endpoint yet. Enable `serviceMonitor.enabled` once a `/metrics` surface exists.
- TLS terminates at the ingress/load-balancer layer, not in this chart — the relay process itself
  cannot terminate TLS.

## PII master key (§13.2, §8.3)

The keyring Secret is **created-if-absent** and **never regenerated on `helm upgrade`**:

- A `lookup` guard reuses the existing Secret's value on upgrade; a fresh 32-byte key is generated
  only on first install. `helm.sh/resource-policy: keep` prevents deletion on uninstall.
- All pods mount the Secret at `piiKeyring.mountPath/piiKeyring.key`, wired to
  `RELAY_PII_KEYRING_FILE`.
- To bring your own key material, set `piiKeyring.secretName` (this chart then manages nothing).

### GitOps / offline rendering (`helm template`, ArgoCD, Flux)

The create-if-absent guard is a plain template that calls `lookup`, not a hook Job — `lookup`
requires install-time RBAC to read Secrets in the target namespace, and it always returns empty
under `helm template` or any offline-render engine (including ArgoCD's and Flux's default
templating, which do not run against a live cluster with those permissions). If `lookup` returns
empty, the template falls into its "no existing Secret" branch and generates a **new** random key
every render — under GitOps this can silently orphan every outstanding `ENC_` token on each sync.

GitOps users **must** create the keyring Secret externally (out-of-band, once) and set
`piiKeyring.secretName` to its name so this template is skipped entirely; do not rely on the
`lookup` guard when the chart is rendered/applied by a GitOps controller.

Keyring format: a single base64(32-byte) master key. (A legacy one-entry
`{"0": "<base64(32-byte key)>"}` object is still accepted for already-provisioned Secrets.)

### Key rotation

Key rotation is not handled by the relay. It will be reintroduced later through a dedicated KMS
store plugin. Until then the keyring holds a single master key; **never** replace it while its
tokens are still outstanding, or those tokens become undecryptable.

## Key values

| Key | Default | Notes |
|-----|---------|-------|
| `image.repository` / `image.tag` | `ghcr.io/wenrixai/wenrix-relay` / appVersion | image ref |
| `autoscaling.enabled` | `true` | HPA on CPU + optional RPS |
| `podDisruptionBudget.minAvailable` | `1` | rolling-update safety |
| `basicAuth.enabled` / `basicAuth.secretName` | `true` / `""` | secret required (via `required`) when enabled |
| `piiKeyring.createIfAbsent` | `true` | generate key once, never on upgrade (GitOps: see above) |
| `autoscaling.targetRequestsPerSecond` | `0` | off by default; needs a custom-metrics adapter exposing `http_server_requests_per_second` (no scrape surface yet) |
| `serviceMonitor.enabled` | `false` | needs a Prometheus scrape endpoint (follow-up) |

Full reference: `values.yaml`.
