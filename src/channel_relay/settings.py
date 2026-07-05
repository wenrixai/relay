"""Global server settings from ``RELAY_*`` environment variables
(see ``openspec/specs/relay-configuration/spec.md``).

Channel definitions live in the JSON config (``config/models.py``); this module holds the
process-level scalars. Secrets are read from mounted files/env, never from the JSON config.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level relay settings, overridable via ``RELAY_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="RELAY_", extra="ignore")

    config_file: str = "/etc/wenrix/relay.json"
    port: int = 8080
    tls_enabled: bool = False
    tls_port: int = 18443
    mtls_enabled: bool = False
    basic_auth_enabled: bool = True
    basic_auth_user: str | None = None
    basic_auth_pass: str | None = None
    dns_resolver: str = "8.8.8.8"
    default_connect_timeout: int = 30
    default_read_timeout: int = 120
    max_inspect_bytes: int = 8_388_608
    telemetry_logs_enabled: bool = True
    telemetry_metrics_enabled: bool = True
    otlp_endpoint: str | None = None
    rules_api_url: str | None = None
    pii_keyring: str | None = None
    pii_keyring_file: str | None = None
    pii_key_epoch_active: int | None = None
    debug: bool = False
