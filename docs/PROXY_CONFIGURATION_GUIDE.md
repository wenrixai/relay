# Wenrix Proxy Configuration Guide

This guide describes how to configure the Wenrix Channel Relay for a customer deployment. It is
intended for infrastructure, security, and integration teams responsible for running the relay in
their own environment.

The relay is deployed in the customer environment and forwards Wenrix traffic to configured travel
channels. Wenrix calls the relay at:

```text
/channel/{channel_name}/{upstream_path}
```

`{channel_name}` selects one configured channel. The remaining path is forwarded to that channel's
configured upstream service.

## Configuration Overview

The relay uses two configuration layers:

| Layer | Purpose | Typical source |
| --- | --- | --- |
| Relay process settings | Port, authentication, telemetry, body-size limits, keyring location | `RELAY_*` environment variables |
| Channel configuration | Channel names, channel types, upstream hosts, PII mode, operation allow-list | JSON file mounted at `RELAY_CONFIG_FILE` |

The default config file path is:

```text
/etc/wenrix/relay.json
```

The relay validates this file during startup. Invalid configuration stops the process before it
serves traffic.

## Required Customer Inputs

Before deployment, collect the following values.

| Input | Description |
| --- | --- |
| Relay image | Versioned image reference supplied by Wenrix. Do not use `latest` in production. |
| Wenrix ingress CIDRs | Source CIDRs allowed to call the relay. Do not expose the relay publicly. |
| Channel egress destinations | CIDRs or network routes required for upstream channel APIs and DNS. |
| TLS certificate | Certificate for the customer-facing HTTPS endpoint. |
| Basic-auth credentials | Credentials Wenrix uses when calling relay routes. |
| Channel list | One entry per upstream channel integration. |
| PII mode | Whether response PII should be encrypted, force-redacted, or left disabled per channel. |
| PII keyring | Required for encrypted PII tokens and some response-auth encryption flows. |
| Telemetry endpoint | Optional OTLP endpoint for logs and metrics. |

## Channel Configuration

The channel configuration file contains a top-level `channels` array. Only `name` and `type` are
required for a minimal channel, but production deployments normally also set `host`, `proxy_pass`,
PII behavior, and authorization rules.

```json
{
  "channels": [
    {
      "name": "sabre-prod",
      "type": "sabre",
      "host": "webservices.platform.sabre.com",
      "proxy_pass": "https://webservices.platform.sabre.com",
      "timeouts": {
        "connect": 30,
        "read": 120
      },
      "pii": {
        "enabled": true,
        "force_redact": false
      },
      "authorization": {
        "allowed_operations": [
          {
            "operation": "GetReservationRQ",
            "version": "^1.0"
          }
        ]
      }
    }
  ]
}
```

### Channel Fields

| Field | Required | Description |
| --- | --- | --- |
| `name` | Yes | Unique channel name used in the route `/channel/{name}/...`. |
| `type` | Yes | Supported channel type. Selects channel-specific parsing and credential behavior. |
| `host` | No | Upstream host. Some channel types have defaults; per-customer hosts should be explicit. |
| `proxy_pass` | No | Full upstream base URL. If omitted and `host` is known, defaults to `https://{host}`. |
| `timeouts.connect` | No | Upstream connect timeout in seconds. Default: `30`. |
| `timeouts.read` | No | Upstream read timeout in seconds. Default: `120`. |
| `credentials` | No | Channel-specific credential fields used for credential swap. Treat real values as secrets. |
| `pii.enabled` | No | Enables response redaction and request de-anonymization for the channel. Default: `false`. |
| `pii.force_redact` | No | Replaces encrypted PII actions with a fixed redacted value. Default: `false`. |
| `authorization.allowed_operations` | No | Optional allow-list of body-parsed operations. Empty means all operations are allowed. |

## Supported Channel Types

| Channel type | Credential keys used by the relay |
| --- | --- |
| `travelfusion` | `login_id`, `xml_login_id`, optional `supplier_parameters` |
| `ba-ndc-direct` | `client_key` |
| `la-ndc-direct` | `api_key`, optional `api_key_header` |
| `farelogix-aa` | `subscription_key` or `api_key`, `username`, `password`, `agent`, `agent_user`, `agent_password`, optional `agent_number` |
| `farelogix-lh` | Same as `farelogix-aa` |
| `farelogix-ua` | Same as `farelogix-aa` |
| `farelogix-ek` | Same as `farelogix-aa` |
| `amadeus` | `soap_security`, optional `soap_security_target_xpath` |
| `sabre` | `soap_security`, optional `soap_security_target_xpath` |
| `travelport` | `soap_security`, optional `soap_security_target_xpath` |

Credential swap is opt-in. If a channel has no `credentials` object, requests are forwarded
transparently apart from header hygiene, authorization, and any enabled PII processing.

Do not place real credentials in committed JSON, Helm values, Terraform variable files, or
ConfigMaps. The Helm and ECS examples in this guide keep channel configuration non-secret. If a
deployment requires relay-managed channel credentials, render those fields from the customer's
approved secret-management workflow at deploy time and do not persist the rendered file outside the
runtime environment.

## PII Configuration

PII processing is configured per channel.

```json
{
  "name": "amadeus-prod",
  "type": "amadeus",
  "host": "nodeD3.production.webservices.amadeus.com",
  "pii": {
    "enabled": true,
    "force_redact": false
  }
}
```

Use these modes:

| Mode | Configuration | When to use |
| --- | --- | --- |
| Disabled | `pii.enabled: false` | The channel does not require relay-side PII processing. |
| Encrypted tokens | `pii.enabled: true`, `force_redact: false` | Wenrix must be able to send encrypted fields back through the relay for de-anonymization. |
| Fixed redaction | `pii.enabled: true`, `force_redact: true` | The customer wants irreversible redaction rather than reversible encrypted tokens. |

Encrypted-token mode requires a PII keyring. The keyring format is:

```json
{
  "0": "BASE64_ENCODED_32_BYTE_KEY"
}
```

Key rotation uses integer epochs:

1. Add a new epoch to the keyring.
2. Set the active epoch to the new value.
3. Keep old epochs until no outstanding tokens reference them.

Never replace or remove an existing epoch while tokens created with that epoch may still be in use.

## Relay Process Settings

The most common `RELAY_*` settings are:

| Setting | Default | Description |
| --- | --- | --- |
| `RELAY_CONFIG_FILE` | `/etc/wenrix/relay.json` | Path to the channel configuration file. |
| `RELAY_PORT` | `8080` | HTTP listen port inside the container. |
| `RELAY_BASIC_AUTH_ENABLED` | `true` | Enables HTTP Basic Auth for relay routes. |
| `RELAY_BASIC_AUTH_USER` | unset | Basic-auth username. Supply from a secret. |
| `RELAY_BASIC_AUTH_PASS` | unset | Basic-auth password. Supply from a secret. |
| `RELAY_DNS_RESOLVER` | `8.8.8.8` | Upstream DNS resolver. |
| `RELAY_DEFAULT_CONNECT_TIMEOUT` | `30` | Default upstream connect timeout in seconds. |
| `RELAY_DEFAULT_READ_TIMEOUT` | `120` | Default upstream read timeout in seconds. |
| `RELAY_MAX_INSPECT_BYTES` | `8388608` | Maximum body size inspected for XML/PII/authorization processing. |
| `RELAY_OTLP_ENDPOINT` | unset | Optional OTLP endpoint in `host:port` form. |
| `RELAY_RULES_API_URL` | unset | Optional rules API. If unset, bundled fallback rules are used. |
| `RELAY_PII_KEYRING` | unset | Inline keyring JSON. Prefer mounted files or managed secrets where available. |
| `RELAY_PII_KEYRING_FILE` | unset | Mounted keyring file path. Takes precedence over inline keyring. |
| `RELAY_PII_KEY_EPOCH_ACTIVE` | highest epoch | Active key epoch for new encrypted tokens. |
| `RELAY_DEBUG` | `false` | Verbose startup behavior. Secrets and PII are still not logged. |

When `RELAY_BASIC_AUTH_ENABLED` is true, both `RELAY_BASIC_AUTH_USER` and
`RELAY_BASIC_AUTH_PASS` must be configured or the relay refuses to start.

## Kubernetes Helm Deployment

Use the Helm chart when deploying into Kubernetes.

```bash
helm install relay deployment/helm/chart \
  --namespace wenrix --create-namespace \
  --set image.tag=v0.1.0 \
  --set-json 'networkPolicy.ingressFromCIDRs=["203.0.113.0/24"]' \
  --set-json 'networkPolicy.egressToCIDRs=["198.51.100.0/24"]' \
  --set config.telemetry.otlpEndpoint=otel-collector.telemetry:4317 \
  --set config.telemetry.otlpHost=10.100.0.10
```

### Helm Values to Configure

| Value | Description |
| --- | --- |
| `image.repository` / `image.tag` | Relay image and version. |
| `config.channels` | Non-secret channel configuration rendered into `/etc/wenrix/relay.json`. |
| `config.env` | Non-secret `RELAY_*` scalar settings. |
| `config.telemetry.otlpEndpoint` | Optional OTLP endpoint. |
| `networkPolicy.ingressFromCIDRs` | CIDRs allowed to reach the relay. Required in production. |
| `networkPolicy.egressToCIDRs` | CIDRs the relay may call for upstream channel APIs. |
| `basicAuth.enabled` | Keep enabled unless another approved client-auth control is in place. |
| `basicAuth.secretName` | Kubernetes Secret with `user` and `pass` keys. |
| `piiKeyring.enabled` | Mount a PII keyring Secret when encrypted PII tokens are used. |
| `piiKeyring.activeEpoch` | Active key epoch for new tokens. |
| `tls.enabled` / `tls.secretName` | Optional inbound TLS material mounted from a Secret. |

Example channel values:

```yaml
config:
  channels:
    - name: sabre-prod
      type: sabre
      host: webservices.platform.sabre.com
      proxy_pass: https://webservices.platform.sabre.com
      pii:
        enabled: true
        force_redact: false
      authorization:
        allowed_operations:
          - operation: GetReservationRQ
            version: "^1.0"
  env:
    RELAY_BASIC_AUTH_ENABLED: "true"
    RELAY_DNS_RESOLVER: "8.8.8.8"
    RELAY_DEFAULT_CONNECT_TIMEOUT: "30"
    RELAY_DEFAULT_READ_TIMEOUT: "120"
    RELAY_MAX_INSPECT_BYTES: "8388608"
```

Secrets should be created separately and referenced by name:

```bash
kubectl create secret generic relay-basic-auth \
  --namespace wenrix \
  --from-literal=user='RELAY_USER' \
  --from-literal=pass='RELAY_PASSWORD'
```

```bash
kubectl create secret generic relay-pii-keyring \
  --namespace wenrix \
  --from-file=keyring.json=./keyring.json
```

Do not store these literal example values in production automation. Generate and store real secrets
through the customer's approved secret-management workflow.

## AWS ECS Deployment

Use the Terraform module under `deployment/terraform` when deploying on ECS Fargate.

The module expects an existing VPC. It creates:

| Component | Purpose |
| --- | --- |
| HTTPS Application Load Balancer | Customer-facing relay endpoint. |
| ECS Fargate service | Relay tasks in private subnets. |
| Security groups | ALB ingress from Wenrix CIDRs; task ingress only from ALB. |
| Secrets Manager secret | PII keyring injected into the task. |
| CloudWatch log group | Relay container logs. |
| Autoscaling policy | CPU and ALB-request based scaling. |

Example `terraform.tfvars` shape:

```hcl
region = "eu-west-1"
name   = "wenrix-relay"
image  = "ghcr.io/wenrixai/wenrix-relay:v0.1.0"

vpc_id             = "vpc-0123456789abcdef0"
public_subnet_ids  = ["subnet-0aaa1111", "subnet-0bbb2222"]
private_subnet_ids = ["subnet-0ccc3333", "subnet-0ddd4444"]

wenrix_ingress_cidrs = ["203.0.113.0/24"]
certificate_arn      = "arn:aws:acm:eu-west-1:111122223333:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

relay_config_json = <<JSON
{
  "channels": [
    {
      "name": "travelport-prod",
      "type": "travelport",
      "proxy_pass": "https://travelport.customer.example",
      "pii": {
        "enabled": true,
        "force_redact": false
      }
    }
  ]
}
JSON

pii_key_epoch_active = 0
otlp_endpoint        = "otel-collector.telemetry.internal:4317"
desired_count        = 2
min_capacity         = 2
max_capacity         = 10
```

Provide the PII keyring out of band:

```bash
export TF_VAR_pii_keyring_json='{"0":"BASE64_ENCODED_32_BYTE_KEY"}'
terraform apply
```

For production, source the value from the customer's approved secret workflow rather than shell
history or committed files.

## Network and Security Requirements

Apply these controls in every production deployment:

| Control | Requirement |
| --- | --- |
| Ingress | Allow only Wenrix source CIDRs or a private connectivity path approved for the customer. |
| Egress | Allow DNS, configured channel APIs, and optional telemetry endpoints only. |
| TLS | Terminate HTTPS at the load balancer or ingress controller using customer-managed certificates. |
| Client auth | Keep Basic Auth enabled unless mTLS or another approved control replaces it. |
| Secrets | Store Basic Auth, PII keyrings, TLS keys, and channel credentials in a secret manager. |
| ConfigMaps / values | Non-secret configuration only. |
| Logs | Do not log request or response bodies, PII, channel credentials, or key material. |
| Scaling | Run at least two replicas/tasks across availability zones for production. |

## Health Checks and Operations

The relay exposes these operational endpoints:

| Endpoint | Authentication | Purpose |
| --- | --- | --- |
| `/liveness` | None | Process liveness. |
| `/readiness` | None | Readiness; returns not-ready when configuration is missing or invalid. |
| `/admin/flare` | Basic Auth required | Redacted diagnostic snapshot for support. |

Use `/readiness` for load-balancer and orchestrator health checks.

The `/admin/flare` response is designed for support diagnostics. It includes runtime details,
readiness status, redacted configuration shape, keyring epoch metadata, rules version, channel
summaries, and metric counters. It does not return secret values.

## Validation Checklist

Before opening traffic to Wenrix, verify:

- The relay starts cleanly with the intended image tag.
- `/readiness` returns `200`.
- Basic Auth is configured and unauthenticated `/channel/...` requests are rejected.
- Ingress is limited to approved Wenrix CIDRs or private connectivity.
- Egress reaches DNS, upstream channel APIs, and the telemetry endpoint if configured.
- `config.channels` contains no plaintext production secrets.
- The PII keyring is present when any channel requires encrypted PII tokens.
- The active PII key epoch exists in the keyring.
- Telemetry and logs are visible in the customer's monitoring platform.
- A test request reaches the expected upstream channel through `/channel/{name}/...`.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Relay does not start | Basic Auth enabled without username/password | Configure `RELAY_BASIC_AUTH_USER` and `RELAY_BASIC_AUTH_PASS`, or explicitly disable Basic Auth only in an approved environment. |
| `/readiness` returns `503` | Missing or invalid channel config | Check the mounted `RELAY_CONFIG_FILE` path and validate the JSON shape. |
| Requests return `401` | Missing or incorrect Basic Auth | Confirm Wenrix is using the configured credentials. |
| Requests return `404` | Unknown channel name | Confirm the route channel name matches a configured `channels[].name`. |
| Requests return `413` | Body exceeds `RELAY_MAX_INSPECT_BYTES` and inspection is required | Increase the limit only after confirming expected message sizes and memory impact. |
| Requests return `502` with XML or credential errors | Payload must be inspected but is malformed or missing expected credential targets | Confirm channel type, upstream operation format, and credential-swap settings. |
| PII tokens cannot be decrypted | Keyring epoch missing or changed | Restore the original epoch key and keep historical epochs until tokens expire. |
| Upstream timeouts | Channel unreachable or timeout too low | Verify egress allow-lists, DNS, channel endpoint, and per-channel timeout values. |

For support escalation, provide the relay version, deployment platform, channel name, readiness
status, relevant request timestamp, trace ID if available, and the redacted `/admin/flare` output.
Do not send plaintext credentials, PII, keyrings, or raw production payload bodies.
