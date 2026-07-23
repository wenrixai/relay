# Design

## OTLP log export

### Mirror the traces/metrics pattern exactly
`observability/tracing.py` and `observability/metrics.py` already establish the house style: a
per-app provider, built from `Settings`, exporting over OTLP/gRPC to `settings.otlp_endpoint`, with a
`Resource` carrying `service.name`/`service.version`, a test-injection hook, and **never** setting
the global provider (so parallel test apps don't fight). Logs follow the same shape:

```python
def build_logger_provider(settings, log_processor=None) -> LoggerProvider:
    resource = Resource.create({OTEL_SERVICE_NAME: SERVICE_NAME, SERVICE_VERSION: __version__})
    provider = LoggerProvider(resource=resource)
    if log_processor is not None:
        provider.add_log_record_processor(log_processor)          # test hook
    elif settings.telemetry_logs_enabled and settings.otlp_endpoint:
        provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=settings.otlp_endpoint)))
    return provider
```

Gate on `logs_enabled AND otlp_endpoint` (same as metrics/traces): no exporter is created when there
is no collector, so a relay with logs enabled but no endpoint — and the whole test suite — never
spawns an exporter retrying a dead endpoint. The batch processor swallows export failures, so a down
Collector never crashes or blocks the relay.

### Loguru → OTel bridge (dual sink)
`configure_logging` keeps its existing `logger.add(sys.stderr, serialize=True, …)` sink and, when a
`logger_provider` is passed, adds a second sink wrapping
`opentelemetry.sdk._logs.LoggingHandler(logger_provider=provider)`. Loguru accepts a
`logging.Handler` as a sink and constructs the `LogRecord` for it. The OTel handler is **not** added
to the stdlib root logger: the existing `InterceptHandler` already funnels stdlib/uvicorn records
into Loguru, so a single Loguru sink is the one bridge point and there is no double emission.

**Decision — keep stderr (dual sink).** The customer said "not stdout/stderr", but the stderr JSON
sink is retained deliberately: it is the CloudWatch/k8s fallback, and it is the only sink available
for errors raised before the provider is built (config/keyring validation in `create_app`/lifespan).
OTLP is added *in addition*. If a future requirement demands suppressing stderr, that becomes a
follow-up toggle; it is out of scope here.

### Wiring order
`create_app` currently calls `configure_logging` before `_build_telemetry`. Reorder so the logger
provider exists first, then `configure_logging(debug=…, logger_provider=telemetry.logger_provider)`.
Store `app.state.logger_provider`; shut it down in the lifespan `finally` next to the meter/tracer
shutdowns.

## Context path

### Why a middleware, not FastAPI `root_path` alone
FastAPI/uvicorn `root_path` only affects self-referential URL generation (OpenAPI, redirects) — it
does **not** make Starlette match an incoming `/<prefix>/…` path against root-mounted routes in a
version-stable way, and whether it strips depends on the ASGI server + Starlette version. The
customer is unsure whether their LB strips the prefix before forwarding. To be correct under **both**
behaviors without reconfiguration, use an explicit prefix-stripping ASGI middleware:

- No-op when `root_path == ""` (today's behavior, byte-for-byte).
- If `scope["path"]` is exactly `<prefix>` or starts with `<prefix>/`, strip the prefix from `path`
  (and `raw_path`) and set `scope["root_path"] = <prefix>` before the app routes the request.
- If the LB already stripped the prefix (path arrives as `/channel/…`), the middleware finds no
  prefix and passes through — the root-mounted routes match as they do today.

This means routes stay declared at root (`/channel/{name}`, `/liveness`, …) — no APIRouter
refactor — and both `/relay/channel/x` and `/channel/x` resolve. `FastAPI(root_path=settings.root_path)`
is still set for correct URL generation (cosmetic; docs are disabled).

### Why the forwarding pipeline is unaffected
`build_target_url` and `find_channel` operate on the route-captured `{path:path}` param and
`request.url.query`, never on `request.url.path`. Once the middleware has stripped the prefix, channel
matching and upstream URL construction see exactly what they see today. Grep confirms zero uses of
`request.url.path` / `scope["root_path"]` in the forwarding path.

### `root_path` normalization
Empty stays empty. Otherwise ensure exactly one leading `/` and no trailing `/`
(`relay` → `/relay`, `/relay/` → `/relay`). A pydantic field validator on `Settings.root_path`.

### Deployment
- Pod-local probes (k8s/ECS) hit the container directly; the middleware tolerates the unprefixed
  form, but probe paths are templated with the prefix for consistency.
- The ALB target-group health check traverses the LB, so its path becomes `<contextPath>/readiness`,
  and a listener path rule matches `<contextPath>/*` (today there is only a default forward action).

## Alternatives considered
- **APIRouter(prefix=…)**: forces all routes under the prefix and 404s the bare form if the LB
  strips — not robust to the unknown LB behavior. Rejected.
- **uvicorn `--root-path` only**: version-dependent stripping; doesn't reliably match `/<prefix>/…`.
  Rejected as the sole mechanism (kept only for URL generation).
- **Suppressing stderr for logs**: rejected for now (loses fallback + pre-provider errors).
