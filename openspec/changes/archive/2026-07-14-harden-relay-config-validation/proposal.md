# Harden relay configuration validation and server runtime defaults

## Why

A deployment review found gaps in the configuration surface:

- Config validation failures re-raise pydantic `ValidationError`, whose message embeds the full
  offending input (including per-channel `credentials` values). The exception propagates uncaught
  through the FastAPI lifespan to uvicorn's stdlib logging and lands in stderr/CloudWatch —
  violating the "never log credentials" guardrail.
- Duplicate channel `name`s validate silently; `find_channel` returns the first match, so a
  duplicate shadows the second channel's routing, credentials, and PII settings with no error.
- `port`/`tls_port` accept any int (`RELAY_PORT=-5` fails obscurely inside uvicorn);
  `proxy_pass`/`host`/`rules_api_url` accept any string, deferring typos to request time.
- `authorization.external` is accepted by the model but never enforced in the pipeline — an
  operator configuring it gets silent no-enforcement with no warning.
- `cli()` starts uvicorn with a 5s default keep-alive (below the ALB's 60s idle timeout — an
  intermittent-502 generator behind AWS ALB) and without `proxy_headers`.

## What Changes

- `load_config` catches `ValidationError` and re-raises a sanitized `ConfigValidationError`
  (field paths + error types only, never values; cause chain suppressed).
- `RelayConfig` rejects duplicate channel names at validation time.
- `port`/`tls_port` constrained to 1–65535; `proxy_pass` and `rules_api_url` must be
  `http(s)://` URLs; `host` must be a bare hostname (no scheme, no path). `otlp_endpoint` stays
  permissive (`host:port` is a valid gRPC form).
- Startup logs a loud WARNING per channel that configures `authorization.external` (accepted but
  not enforced in this version).
- `cli()` passes `timeout_keep_alive=75`, `proxy_headers=True`, `forwarded_allow_ips="*"` to
  uvicorn (task security groups restrict ingress to the load balancer).

## Capabilities

### Modified Capabilities
- `relay-configuration`: sanitized abort-on-invalid-config, channel-name uniqueness, port/URL
  field validation, unenforced-external-authorization startup warning.

## Impact

- `src/channel_relay/config/loader.py`: `ConfigValidationError`, sanitized re-raise.
- `src/channel_relay/config/models.py`: uniqueness + URL/host validators.
- `src/channel_relay/settings.py`: port range constraints, `rules_api_url` scheme check.
- `src/channel_relay/main.py`: `warn_unenforced_config` in lifespan; uvicorn kwargs in `cli()`.
- `tests/unit/test_config.py`, `tests/unit/test_main_startup.py`: new/updated tests.
