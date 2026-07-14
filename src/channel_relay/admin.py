"""Authenticated admin diagnostics payloads."""

from __future__ import annotations

import os
import platform
import socket
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request

from channel_relay import __version__
from channel_relay.config.models import ChannelConfig, RelayConfig
from channel_relay.health import readiness_reasons
from channel_relay.middleware.auth import auth_active, mtls_material_complete
from channel_relay.observability.metrics import RelayMetrics
from channel_relay.pii.crypto import Keyring
from channel_relay.settings import Settings


def _safe_url(value: str | None) -> str | None:
    """Return a URL without userinfo, query, or fragment."""
    if value is None:
        return None
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    netloc = parsed.hostname or ""
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _channel_snapshot(channel: ChannelConfig) -> dict[str, Any]:
    return {
        "name": channel.name,
        "type": channel.type.value,
        "host": channel.host,
        "proxy_pass": _safe_url(channel.proxy_pass),
        "timeouts": {
            "connect": channel.timeouts.connect,
            "read": channel.timeouts.read,
        },
        "credential_keys": sorted(channel.credential_values),
        "credential_count": len(channel.credential_values),
        "credential_swap_enabled": channel.credential_swap_enabled,
        "pii_enabled": channel.pii.enabled,
        "authorization": {
            "enabled": channel.authorization.enabled,
            "allowed_operations_count": len(channel.authorization.allowed_operations),
            "external_configured": channel.authorization.external is not None,
        },
    }


def diagnostics_snapshot(request: Request) -> dict[str, Any]:
    """Build the redacted `/admin/flare` response."""
    settings: Settings = request.app.state.settings
    config: RelayConfig | None = request.app.state.config
    metrics: RelayMetrics = request.app.state.metrics
    keyring: Keyring | None = request.app.state.keyring
    started_at: float = request.app.state.started_at
    reasons = readiness_reasons(config)
    rules = request.app.state.rules

    return {
        "runtime": {
            "version": __version__,
            "python": platform.python_version(),
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "uptime_seconds": max(0.0, time.time() - started_at),
            "debug": settings.debug,
        },
        "readiness": {
            "status": "not_ready" if reasons else "ready",
            "reasons": reasons,
        },
        "settings": {
            "config_file": settings.config_file,
            "port": settings.port,
            "tls_enabled": settings.tls_enabled,
            "tls_port": settings.tls_port,
            "mtls_enabled": settings.mtls_enabled,
            # Enforcement, not intent: true only when the cert/key/CA material is actually present
            # so the flag alone never over-reports protection.
            "mtls_enforced": mtls_material_complete(settings),
            "basic_auth": {
                "enabled": settings.basic_auth_enabled,
                "configured": auth_active(settings),
            },
            "dns_resolver": settings.dns_resolver,
            "default_connect_timeout": settings.default_connect_timeout,
            "default_read_timeout": settings.default_read_timeout,
            "max_inspect_bytes": settings.max_inspect_bytes,
            "telemetry_logs_enabled": settings.telemetry_logs_enabled,
            "telemetry_metrics_enabled": settings.telemetry_metrics_enabled,
            "otlp_endpoint_configured": settings.otlp_endpoint is not None,
            "rules_api_url_configured": settings.rules_api_url is not None,
            "pii_keyring_configured": settings.pii_keyring is not None or settings.pii_keyring_file is not None,
            "pii_keyring_file_configured": settings.pii_keyring_file is not None,
            "pii_key_epoch_active_configured": settings.pii_key_epoch_active is not None,
        },
        "keyring": {
            "configured": keyring is not None,
            "active_epoch": keyring.active_epoch if keyring is not None else None,
            "epochs": list(keyring.epochs) if keyring is not None else [],
        },
        "rules": {
            "loaded": rules is not None,
            "rules_version": rules.rules_version if rules is not None else None,
        },
        "channels": [_channel_snapshot(channel) for channel in config.channels] if config is not None else [],
        "statistics": metrics.snapshot(),
    }
