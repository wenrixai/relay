# wenrix-relay Helm chart

Hardened Kubernetes deployment for the Wenrix Channel Relay (PROJECT.md §13.5, §13.2).

## Install

```bash
helm install relay deployment/helm/chart \
  --namespace wenrix --create-namespace \
  --set image.tag=v0.1.0 \
  --set-json 'networkPolicy.ingressFromCIDRs=["10.0.0.0/8"]' \
  --set-json 'networkPolicy.egressToCIDRs=["203.0.113.0/24"]' \
  --set config.telemetry.otlpEndpoint=http://otel-collector.telemetry:4317 \
  --set config.telemetry.otlpHost=10.100.0.10
```

Channels are set via `config.channels` (rendered into a ConfigMap as `/etc/wenrix/relay.json`).
Secrets are **never** placed in values or the ConfigMap.

## Security defaults (§13.5)

- Pod/container run as non-root (`runAsNonRoot`, numeric UID), `readOnlyRootFilesystem: true`
  (writable `/tmp` emptyDir only), `allowPrivilegeEscalation: false`, all capabilities dropped,
  seccomp `RuntimeDefault`.
- CPU/memory requests == limits at the perf baseline (1000m / 512Mi).
- Default-deny `NetworkPolicy`: ingress only from configured sources; egress only to DNS, channel
  host CIDRs, and the telemetry endpoint.
- `HorizontalPodAutoscaler` (CPU + optional RPS) and `PodDisruptionBudget`.
- Probes to `/liveness` and `/readiness`.
- `ServiceMonitor` is shipped **disabled** — the relay is OTLP-push only and has no Prometheus
  scrape endpoint yet. Enable `serviceMonitor.enabled` once a `/metrics` surface exists.

## PII master key (§13.2, §8.3)

The keyring Secret is **created-if-absent** and **never regenerated on `helm upgrade`**:

- A `lookup` guard reuses the existing Secret's value on upgrade; a fresh 32-byte key is generated
  only on first install. `helm.sh/resource-policy: keep` prevents deletion on uninstall.
- All pods mount the Secret at `piiKeyring.mountPath/piiKeyring.key`, wired to
  `RELAY_PII_KEYRING_FILE`.
- To bring your own key material, set `piiKeyring.secretName` (this chart then manages nothing).

Keyring format: `{"<epoch_int>": "<base64(32-byte key)>"}`.

### Epoch rotation

Rotation uses the 1-byte key epoch — **never** replace an existing epoch's key while its tokens are
still outstanding, or those tokens become undecryptable:

1. Add a new epoch entry to the keyring JSON (keep all prior epochs).
2. Set `piiKeyring.activeEpoch` to the new epoch. New tokens encrypt under it; old tokens still
   decrypt under their original epoch.
3. Retire an old epoch only once no outstanding token references it.

## Key values

| Key | Default | Notes |
|-----|---------|-------|
| `image.repository` / `image.tag` | `ghcr.io/wenrixai/wenrix-relay` / appVersion | image ref |
| `autoscaling.enabled` | `true` | HPA on CPU + optional RPS |
| `podDisruptionBudget.minAvailable` | `1` | rolling-update safety |
| `networkPolicy.ingressFromCIDRs` | `[]` | Wenrix client sources (required in practice) |
| `networkPolicy.egressToCIDRs` | `[]` | channel host CIDRs (HTTPS/443) |
| `piiKeyring.createIfAbsent` | `true` | generate key once, never on upgrade |
| `serviceMonitor.enabled` | `false` | needs a Prometheus scrape endpoint (follow-up) |

Full reference: `values.yaml`.
