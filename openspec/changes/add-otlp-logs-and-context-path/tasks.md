## 1. OTLP log export — provider

- [ ] 1.1 Write failing unit test (`tests/unit/test_logs.py`): with an injected in-memory
      `log_processor` (`SimpleLogRecordProcessor(InMemoryLogExporter())`) via
      `create_app(log_processor=…)`, a `logger.info(...)` call produces a log record in the exporter.
- [ ] 1.2 Write failing unit test: the log `Resource` carries `service.name == "wenrix-channel-relay"`
      and `service.version == __version__`.
- [ ] 1.3 Write failing unit test: disabled path — with `RELAY_TELEMETRY_LOGS_ENABLED` off and no
      injected processor, no OTLP exporter is attached (mirror `test_tracing.py` disabled convention).
- [ ] 1.4 Add `observability/logs.py` with `build_logger_provider(settings, log_processor=None)`
      mirroring `build_tracer_provider` (Resource, gate on `telemetry_logs_enabled and otlp_endpoint`,
      `BatchLogRecordProcessor(OTLPLogExporter(endpoint=…))`).
- [ ] 1.5 Run tests; confirm green.

## 2. OTLP log export — Loguru bridge (dual sink)

- [ ] 2.1 Write failing unit test: with a logger provider wired, the stderr JSON sink STILL emits a
      valid JSON line (dual-sink) — StringIO Loguru sink like `test_logging.py`.
- [ ] 2.2 Extend `configure_logging(*, debug=False, logger_provider=None)` in
      `observability/logging.py`: keep the stderr sink; when `logger_provider` is set, add an OTel
      `LoggingHandler(logger_provider=…)` as an additional Loguru sink. Do not add it to the stdlib
      root logger. Preserve idempotency.
- [ ] 2.3 Run tests; confirm green.

## 3. OTLP log export — main.py wiring

- [ ] 3.1 Write failing integration test: `create_app()` sets `app.state.logger_provider`; with logs
      enabled + injected processor, records flow; provider is shut down cleanly on lifespan exit.
- [ ] 3.2 Add `logger_provider` field to `_Telemetry`; build it in `_build_telemetry` (new
      `log_processor` param), gated `settings.telemetry_logs_enabled or log_processor is not None`.
- [ ] 3.3 Add `log_processor: LogRecordProcessor | None = None` to `create_app`; thread through.
- [ ] 3.4 Reorder so telemetry is built before `configure_logging`; call
      `configure_logging(debug=…, logger_provider=telemetry.logger_provider)`.
- [ ] 3.5 Store `app.state.logger_provider`; shut it down in the lifespan `finally` (guarded).
- [ ] 3.6 Run tests; confirm green.

## 4. Context path — setting

- [ ] 4.1 Write failing unit test: `Settings(root_path="relay").root_path == "/relay"`;
      `"/relay/"` → `"/relay"`; `""` → `""`.
- [ ] 4.2 Add `root_path: str = ""` to `Settings` with a normalizing field validator (leading slash,
      no trailing slash). Env var `RELAY_ROOT_PATH`.
- [ ] 4.3 Run tests; confirm green.

## 5. Context path — middleware + wiring

- [ ] 5.1 Write failing integration test (`tests/unit/test_context_path.py`): with
      `RELAY_ROOT_PATH=/relay`, `GET /relay/liveness` and `GET /relay/readiness` route correctly,
      `/relay/channel/<name>` forwards, AND the bare `/liveness` / `/channel/<name>` forms still work
      (LB-stripped case). With no `root_path`, only the root forms exist (today's behavior).
- [ ] 5.2 Add `middleware/context_path.py`: prefix-stripping ASGI middleware (no-op on empty prefix;
      strips `<prefix>`/`<prefix>/…` from `path`/`raw_path`, sets `scope["root_path"]`).
- [ ] 5.3 Wire it in `create_app` only when `settings.root_path` is set; pass
      `root_path=settings.root_path` to `FastAPI(...)`.
- [ ] 5.4 Add a prefixed `TestClient` fixture variant in `tests/conftest.py`.
- [ ] 5.5 Run tests; confirm green. Confirm existing `test_forwarder.py` / `test_health.py` still pass.

## 6. Deployment + diagnostics + docs

- [ ] 6.1 Helm: add `config.contextPath` value → `RELAY_ROOT_PATH` env in `deployment.yaml`; template
      liveness/readiness probe paths with the prefix; update `values.yaml` + chart README/NOTES.
- [ ] 6.2 Terraform (`main.tf`): ALB target-group `HealthCheckPath` → `<contextPath>/readiness`; add a
      `<contextPath>/*` listener path rule; add the variable + `tfvars.example`.
- [ ] 6.3 CloudFormation (`wenrix-relay.yaml`): `HealthCheckPath`, ECS container health check, and a
      listener path rule parameterized by a context-path parameter.
- [ ] 6.4 Add `root_path` to `/admin/flare` redacted diagnostics (`admin.py`) and a test asserting it.
- [ ] 6.5 Update `docs/PROJECT.md` §11 (logs now exported to OTLP; context-path note) and the
      telemetry/config sections.
- [ ] 6.6 `just helm-test`; confirm chart render/assertions pass.

## 7. Gates and spec sync

- [ ] 7.1 Run `just lint`, `just types`, `just pylint`, `just cov` (85% gate) locally; all green.
- [ ] 7.2 Confirm `uv.lock` is unchanged (no new dependency for OTLP log export).
- [ ] 7.3 Manual checks: OTLP logs land at a local collector + stderr still emits;
      `RELAY_ROOT_PATH=/relay` serves prefixed and bare routes.
- [ ] 7.4 Run `openspec archive add-otlp-logs-and-context-path` (or `opsx:archive`) once merged, to
      sync the spec deltas into `openspec/specs/`.
