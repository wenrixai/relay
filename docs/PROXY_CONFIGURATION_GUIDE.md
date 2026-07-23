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
configured upstream service. `/channel/{channel_name}` is also supported as the empty-path
compatibility form and follows the same processing pipeline.

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
        "enabled": true,
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
| `credentials.enabled` | No | Enables channel-specific credential swap. Default: `false`. |
| `credentials.<key>` | No | Channel-specific credential fields used for credential swap when enabled. Treat real values as secrets. |
| `pii.enabled` | No | Enables response redaction and request de-anonymization for the channel. Default: `false`. |
| `pii.force_redact` | No | Replaces encrypted PII actions with a fixed redacted value. Default: `false`. |
| `authorization.enabled` | No | Enables operation allow-list enforcement. Default: `false`. |
| `authorization.allowed_operations` | No | Optional allow-list of body-parsed operations when authorization is enabled. Empty means all operations are allowed. |

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
| `travelport` | `username`, `password` |

Credential swap is opt-in. If `credentials.enabled` is omitted or false, requests are forwarded
transparently apart from header hygiene, authorization, and any enabled PII processing, even when
credential fields are present in the object.

Do not place real credentials in committed JSON, Helm values, Terraform variable files, or
ConfigMaps. The Helm and ECS examples in this guide keep channel configuration non-secret. If a
deployment requires relay-managed channel credentials, render those fields from the customer's
approved secret-management workflow at deploy time and do not persist the rendered file outside the
runtime environment.

### Travelport Universal API credentials

Travelport SOAP/XML authentication is an HTTP Basic header, not a SOAP `Security` element. For an
enabled Travelport channel, the runtime-rendered secret configuration has this shape:

```json
{
  "name": "travelport-prod",
  "type": "travelport",
  "proxy_pass": "https://emea.universal-api.travelport.com/B2BGateway/connect/uAPI",
  "credentials": {
    "enabled": true,
    "username": "ASSIGNED_USERNAME_FROM_SECRET_STORE",
    "password": "ASSIGNED_PASSWORD_FROM_SECRET_STORE"
  }
}
```

The relay creates `Authorization: Basic <base64>` from
`Universal API/<username>:<password>` and overwrites any caller-supplied `Authorization` casing.
Configure the bare assigned username: do not include `Universal API/` and do not pre-encode the
credential pair.

Migration is intentionally fail-fast. Existing Travelport configurations must remove
`soap_security`, `soap_username`, and `soap_password`; enabled channels containing those obsolete
keys or an incomplete `username`/`password` pair do not start. Travelport session keys are encrypted
on responses and restored in the documented `SessTok/@id` and request `SessionKey` attributes, so an
enabled Travelport credential swap requires `RELAY_PII_KEYRING` or `RELAY_PII_KEYRING_FILE` even when
`pii.enabled` is false. Keep the master key stable until all outstanding sessions have expired.

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

Encrypted-token mode requires a PII keyring. The keyring source is a single base64-encoded
32-byte master key:

```
BASE64_ENCODED_32_BYTE_KEY
```

A legacy one-entry `{"0": "BASE64_ENCODED_32_BYTE_KEY"}` object is still accepted for
already-provisioned secrets.

Key rotation is not handled by the relay. It will be reintroduced later through a dedicated KMS
store plugin. Until then, never replace or remove the master key while tokens created with it may
still be in use — doing so makes those tokens undecryptable.

### Supported content for inspection

PII processing and structural body credential handling support XML/SOAP only. Gzip-encoded XML is
decoded for inspection and processed structurally. JSON, MTOM/multipart, deflate, and unknown content
can pass through opaquely only when the channel configuration does not require body inspection.

If an unsupported request body requires inspection, the relay rejects it with HTTP 415 and reason
`unsupported_content_type` without contacting the channel. If an unsupported upstream response
requires PII redaction or structural credential cleanup, the relay returns HTTP 502 with the same
reason and does not return the upstream body.

## Relay Process Settings

The most common `RELAY_*` settings are:

| Setting | Default | Description |
| --- | --- | --- |
| `RELAY_CONFIG_FILE` | `/etc/wenrix/relay.json` | Path to the channel configuration file. |
| `RELAY_PORT` | `8080` | HTTP listen port inside the container. |
| `RELAY_BASIC_AUTH_ENABLED` | `true` | Enables HTTP Basic Auth for relay routes. |
| `RELAY_BASIC_AUTH_USER` | unset | Basic-auth username. Supply from a secret. |
| `RELAY_BASIC_AUTH_PASS` | unset | Basic-auth password. Supply from a secret. |
| `RELAY_DNS_RESOLVER` | unset (native/OS resolver) | Pin a specific upstream DNS resolver; unset uses the system resolver. |
| `RELAY_DEFAULT_CONNECT_TIMEOUT` | `30` | Default upstream connect timeout in seconds. |
| `RELAY_DEFAULT_READ_TIMEOUT` | `120` | Default upstream read timeout in seconds. |
| `RELAY_MAX_INSPECT_BYTES` | `8388608` | Maximum body size inspected for XML/PII/authorization processing. |
| `RELAY_OTLP_ENDPOINT` | unset | Optional OTLP/gRPC endpoint for metrics and traces. URL form (`http://host:4317`) is recommended; a bare `host:port` is also accepted. |
| `RELAY_TELEMETRY_TRACES_ENABLED` | `false` | Opt-in OpenTelemetry traces over the forward pipeline. Requires `RELAY_OTLP_ENDPOINT` for export. |
| `RELAY_PII_KEYRING` | unset | Inline keyring JSON. Prefer mounted files or managed secrets where available. |
| `RELAY_PII_KEYRING_FILE` | unset | Mounted keyring file path. Takes precedence over inline keyring. |
| `RELAY_DEBUG` | `false` | Verbose startup behavior. Secrets and PII are still not logged. |

When `RELAY_BASIC_AUTH_ENABLED` is true, both `RELAY_BASIC_AUTH_USER` and
`RELAY_BASIC_AUTH_PASS` must be configured or the relay refuses to start.

## Kubernetes Helm Deployment

Use the Helm chart when deploying into Kubernetes.

The chart ships no `NetworkPolicy`: apply ingress/egress restrictions with your cluster or cloud
controls (security groups, a customer-managed `NetworkPolicy`, service mesh policy, etc.) alongside
the chart. The chart also does not terminate TLS; terminate HTTPS at your ingress controller or
load balancer in front of the Service.

Create the basic-auth Secret first, then reference it by name — `basicAuth.secretName` is required
whenever `basicAuth.enabled` is true (the default):

```bash
kubectl create secret generic relay-basic-auth \
  --namespace wenrix --create-namespace \
  --from-literal=user='RELAY_USER' \
  --from-literal=pass='RELAY_PASSWORD'

helm install relay deployment/helm/chart \
  --namespace wenrix --create-namespace \
  --set image.tag=v0.1.0 \
  --set basicAuth.secretName=relay-basic-auth \
  --set config.telemetry.otlpEndpoint=http://otel-collector.telemetry:4317
```

### Helm Values to Configure

| Value | Description |
| --- | --- |
| `image.repository` / `image.tag` | Relay image and version. |
| `config.channels` | Non-secret channel configuration rendered into `/etc/wenrix/relay.json`. |
| `config.env` | Non-secret `RELAY_*` scalar settings. |
| `config.telemetry.otlpEndpoint` | Optional OTLP endpoint. |
| `basicAuth.enabled` | Keep enabled unless another approved client-auth control is in place. |
| `basicAuth.secretName` | Required when `basicAuth.enabled` is true. Kubernetes Secret with `user` and `pass` keys. |
| `piiKeyring.enabled` | Mount a PII keyring Secret when encrypted PII tokens are used. |

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
        enabled: true
        allowed_operations:
          - operation: GetReservationRQ
            version: "^1.0"
  env:
    RELAY_BASIC_AUTH_ENABLED: "true"
    RELAY_DEFAULT_CONNECT_TIMEOUT: "30"
    RELAY_DEFAULT_READ_TIMEOUT: "120"
    RELAY_MAX_INSPECT_BYTES: "8388608"
```

The basic-auth Secret is created above, before `helm install`. The PII keyring Secret is created
separately and referenced by name (or left to the chart's create-if-absent hook — see
`deployment/helm/chart/README.md`):

```bash
kubectl create secret generic relay-pii-keyring \
  --namespace wenrix \
  --from-file=keyring.json=./keyring.json
```

Do not store these literal example values in production automation. Generate and store real secrets
through the customer's approved secret-management workflow.

## AWS ECS Deployment

Use the Terraform module under `deployment/terraform`, or the equivalent CloudFormation template
under `deployment/cloudformation`, when deploying on ECS Fargate. Both automate the same hardened
topology described below. If you cannot adopt either automation, `docs/ECS_MANUAL_DEPLOYMENT.md`
walks through the same topology with plain AWS CLI (and console) steps.

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

otlp_endpoint        = "http://otel-collector.telemetry.internal:4317"
desired_count        = 2
min_capacity         = 2
max_capacity         = 10
```

Provide the PII keyring out of band:

```bash
export TF_VAR_pii_keyring_json="BASE64_ENCODED_32_BYTE_KEY"
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
readiness status, redacted configuration shape, whether a keyring is configured, rules version, channel
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
| PII tokens cannot be decrypted | Master key missing or changed | Restore the original master key; it must stay stable while tokens are outstanding. |
| Upstream timeouts | Channel unreachable or timeout too low | Verify egress allow-lists, DNS, channel endpoint, and per-channel timeout values. |

For support escalation, provide the relay version, deployment platform, channel name, readiness
status, relevant request timestamp, trace ID if available, and the redacted `/admin/flare` output.
Do not send plaintext credentials, PII, keyrings, or raw production payload bodies.
