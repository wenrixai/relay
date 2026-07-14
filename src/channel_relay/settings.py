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
    tls_enabled: bool = False
    tls_port: int = Field(default=18443, ge=1, le=65535)
    mtls_enabled: bool = False
    # mTLS material: server cert/key for the TLS listener and the CA bundle used to verify
    # client certificates. All three are required when mtls_enabled (validated at startup).
    tls_cert_file: str | None = None
    tls_key_file: str | None = None
    mtls_ca_file: str | None = None
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

    @field_validator("rules_api_url")
    @classmethod
    def _validate_rules_api_url(cls, value: str | None) -> str | None:
        """Fail at startup, not at the one-shot rules fetch. ``otlp_endpoint`` stays
        permissive: bare ``host:port`` is a valid gRPC exporter form."""
        if value is not None and not value.startswith(("http://", "https://")):
            msg = "rules_api_url must be an http:// or https:// URL"
            raise ValueError(msg)
        return value
