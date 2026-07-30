"""Global server settings from ``RELAY_*`` environment variables
(see ``openspec/specs/relay-configuration/spec.md``).

Channel definitions live in the JSON config (``config/models.py``); this module holds the
process-level scalars. Secrets are read from mounted files/env, never from the JSON config.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level relay settings, overridable via ``RELAY_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="RELAY_", extra="ignore")

    config_file: str = "/etc/wenrix/relay.json"
    port: int = Field(default=8080, ge=1, le=65535)
    # Context path the relay serves all routes under (e.g. behind an ALB routing rule). Empty
    # means root-only serving (the default). See relay-configuration / transparent-relay specs.
    root_path: str = ""
    tls_enabled: bool = False
    tls_port: int = Field(default=18443, ge=1, le=65535)
    mtls_enabled: bool = False
    basic_auth_enabled: bool = True
    basic_auth_user: str | None = None
    basic_auth_pass: str | None = None
    # Unset uses the OS/native resolver; only set to pin a specific upstream resolver.
    dns_resolver: str | None = None
    default_connect_timeout: int = 30
    default_read_timeout: int = 120
    max_inspect_bytes: int = 8_388_608
    # Upstream httpx connection-pool tuning (defaults raise httpx's 100/20/None ceilings for
    # a high-throughput single-process relay; scaling stays horizontal via replicas).
    max_connections: int = Field(default=200, ge=1)
    max_keepalive_connections: int = Field(default=50, ge=0)
    keepalive_expiry: float = Field(default=30.0, ge=0.0)
    # Connection-establishment retries only (httpcore retries a failed TCP/TLS connect before
    # any request bytes are sent, so a retry here can never duplicate an upstream side effect).
    # No retry ever happens once bytes have been written to the socket (§10.5, D12).
    upstream_connect_retries: int = Field(default=2, ge=0)
    # The relay's single upstream TLS policy: verifying by default, and all-or-nothing — setting
    # this false disables server-certificate verification for *every* channel this process serves.
    # There is no per-channel opt-out; never set false in production.
    upstream_tls_verify: bool = True
    telemetry_logs_enabled: bool = True
    telemetry_metrics_enabled: bool = True
    # Traces are opt-in (unlike logs/metrics): spans add per-request overhead and need a
    # collector; enable explicitly per environment (§11).
    telemetry_traces_enabled: bool = False
    otlp_endpoint: str | None = None
    pii_keyring: str | None = None
    pii_keyring_file: str | None = None
    debug: bool = False
    # Logs the full (trimmed) request/response body at DEBUG level for every relayed call.
    # Bodies may carry plaintext PII (de-anonymized request / pre-redaction response) — never
    # enable in production. A startup warning is emitted whenever this is on (§11).
    debug_mode: bool = False
    debug_mode_max_body_bytes: int = Field(default=65_536, ge=0)

    @field_validator("root_path")
    @classmethod
    def _normalize_root_path(cls, value: str) -> str:
        """Empty stays empty; otherwise exactly one leading ``/`` and no trailing ``/``."""
        trimmed = value.strip().strip("/")
        return f"/{trimmed}" if trimmed else ""
