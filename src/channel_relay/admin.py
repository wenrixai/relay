"""Authenticated admin diagnostics payloads."""

from __future__ import annotations

import os
import platform
import socket
import time
from collections import Counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request

from channel_relay import __version__
from channel_relay.config.models import ChannelConfig, RelayConfig
from channel_relay.health import readiness_reasons
from channel_relay.middleware.auth import auth_active
from channel_relay.observability.metrics import RelayMetrics
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.rules import RuleSet
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


def _rules_snapshot(rules: RuleSet | None) -> dict[str, Any]:
    if rules is None:
        return {
            "loaded": False,
            "schema_version": None,
            "rules_version": None,
            "rule_count": 0,
            "by_rule_type": {},
            "by_pii_type": {},
            "by_channel": {},
            "by_action": {},
        }
    by_rule_type: Counter[str] = Counter()
    by_pii_type: Counter[str] = Counter()
    by_channel: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    for rule in rules.rules:
        by_rule_type[rule.rule_type] += 1
        by_pii_type[rule.pii_type.value] += 1
        by_channel[rule.channel] += 1
        by_action[rule.action.method] += 1
    return {
        "loaded": True,
        "schema_version": rules.schema_version,
        "rules_version": rules.rules_version,
        "rule_count": len(rules.rules),
        "by_rule_type": dict(sorted(by_rule_type.items())),
        "by_pii_type": dict(sorted(by_pii_type.items())),
        "by_channel": dict(sorted(by_channel.items())),
        "by_action": dict(sorted(by_action.items())),
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
            "debug_mode": settings.debug_mode,
        },
        "readiness": {
            "status": "not_ready" if reasons else "ready",
            "reasons": reasons,
        },
        "settings": {
            "config_file": settings.config_file,
            "port": settings.port,
            "root_path": settings.root_path,
            "tls_enabled": settings.tls_enabled,
            "tls_port": settings.tls_port,
            "mtls_enabled": settings.mtls_enabled,
            "basic_auth": {
                "enabled": settings.basic_auth_enabled,
                "configured": auth_active(settings),
            },
            "dns_resolver": settings.dns_resolver,
            "default_connect_timeout": settings.default_connect_timeout,
            "default_read_timeout": settings.default_read_timeout,
            "max_inspect_bytes": settings.max_inspect_bytes,
            "upstream_tls_verify": settings.upstream_tls_verify,
            "telemetry_logs_enabled": settings.telemetry_logs_enabled,
            "telemetry_metrics_enabled": settings.telemetry_metrics_enabled,
            "otlp_endpoint_configured": settings.otlp_endpoint is not None,
            "pii_keyring_configured": settings.pii_keyring is not None or settings.pii_keyring_file is not None,
            "pii_keyring_file_configured": settings.pii_keyring_file is not None,
        },
        "keyring": {
            "configured": keyring is not None,
        },
        "rules": _rules_snapshot(rules),
        "channels": [_channel_snapshot(channel) for channel in config.channels] if config is not None else [],
        "statistics": metrics.snapshot(),
    }
