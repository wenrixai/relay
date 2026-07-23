## Why

Two operator asks from a customer running the relay behind an ALB into an OTel Collector:

1. **Logs to the same OTLP endpoint as metrics.** Today the relay exports metrics (and opt-in
   traces) over OTLP/gRPC to `RELAY_OTLP_ENDPOINT`, but logs only go to stderr via Loguru. The
   customer wants logs delivered to the *same* Collector alongside metrics, so the three signals
   correlate in one place instead of logs living only in stdout/stderr. The
   `RELAY_TELEMETRY_LOGS_ENABLED` setting already exists but is wired to nothing.

2. **Serve under a configurable context path.** The customer's standard routing is
   `https://<load-balancer>:443/<service_context_path>`, where `<service_context_path>` is both the
   LB routing rule and the service's own context path. The relay currently serves only at root
   (`/channel/{name}`, `/liveness`, …), so in their dev environment they had to provision a separate
   port as a workaround. They want the relay to actually serve under a configurable prefix.

## What Changes

- **OTLP log export (default on, gated).** Add an OTLP/gRPC log exporter mirroring the existing
  metrics/traces pattern: a per-app `LoggerProvider` built from settings, exporting to the shared
  `RELAY_OTLP_ENDPOINT` only when `RELAY_TELEMETRY_LOGS_ENABLED` is true **and** an endpoint is
  configured. Loguru gains a second sink bridging records to the provider. The stderr JSON sink is
  **kept** (dual-sink) so operators retain the CloudWatch/k8s fallback and pre-startup errors. No new
  dependencies (the OTLP log SDK/exporter is already installed).

- **Configurable context path (default off).** Add a `RELAY_ROOT_PATH` process setting (default
  `""`). When set, the relay serves all its routes under that prefix. Implemented with a small
  prefix-stripping ASGI middleware that tolerates both LB behaviors — whether the LB forwards the
  full path (incl. prefix) or strips it — so the relay works without reconfiguration in either case.
  Empty `RELAY_ROOT_PATH` preserves today's root-only behavior exactly.

## Capabilities

### New Capabilities
(none — both extend existing capabilities)

### Modified Capabilities
- `observability`: adds an OTLP log-export requirement alongside the existing metrics OTLP export;
  logs are delivered to the same endpoint as metrics/traces, gated on the logs-enabled flag and a
  configured endpoint, while the structured stderr JSON sink is retained.
- `relay-configuration`: adds the `RELAY_ROOT_PATH` setting, its default (`""`), and normalization
  rules, alongside the existing telemetry and networking settings.
- `transparent-relay`: adds the context-path serving requirement — every served route (data-plane,
  health, admin) is reachable under the configured prefix, and channel matching / upstream URL
  construction are unaffected by it.

## Impact

- `observability/logs.py` (new): `build_logger_provider`.
- `observability/logging.py`: `configure_logging` gains a `logger_provider` param and an OTel sink.
- `main.py`: `_Telemetry`/`_build_telemetry`/`create_app` thread a logger provider and a
  `log_processor` test hook; lifespan shuts the provider down; `FastAPI(root_path=…)` and the new
  context-path middleware wired from settings.
- `middleware/context_path.py` (new): prefix-stripping ASGI middleware.
- `settings.py`: `root_path` field + normalizing validator.
- Deployment: Helm `config.contextPath` → `RELAY_ROOT_PATH` and templated probe paths; Terraform/CFN
  ALB target-group health-check path and a `<contextPath>/*` listener rule.
- No change to PII crypto, credential swap, the token format, or the forwarding pipeline stages.
