"""Validation of process-level ``RELAY_*`` settings (ports, URL-shaped fields)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from channel_relay.settings import Settings


@pytest.mark.parametrize("port", [0, -5, 65536])
def test_port_out_of_range_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(port=port)


@pytest.mark.parametrize("port", [1, 8080, 65535])
def test_port_in_range_accepted(port: int) -> None:
    assert Settings(port=port).port == port


@pytest.mark.parametrize("port", [0, 65536])
def test_tls_port_out_of_range_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(tls_port=port)


def test_otlp_endpoint_stays_permissive() -> None:
    # Bare host:port is a valid gRPC exporter form; must not be rejected.
    assert Settings(otlp_endpoint="collector:4317").otlp_endpoint == "collector:4317"


def test_telemetry_traces_disabled_by_default() -> None:
    # Traces are opt-in, unlike logs/metrics (§11).
    settings = Settings()
    assert settings.telemetry_traces_enabled is False
    assert settings.telemetry_metrics_enabled is True


def test_telemetry_traces_env_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELAY_TELEMETRY_TRACES_ENABLED", "true")
    assert Settings().telemetry_traces_enabled is True


def test_upstream_tls_verify_defaults_on() -> None:
    # Verifying by default: the insecure path must always be an explicit operator override.
    assert Settings().upstream_tls_verify is True


def test_upstream_tls_verify_env_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELAY_UPSTREAM_TLS_VERIFY", "false")
    assert Settings().upstream_tls_verify is False


def test_debug_mode_defaults_off() -> None:
    settings = Settings()
    assert settings.debug_mode is False
    assert settings.debug_mode_max_body_bytes == 65_536


def test_debug_mode_max_body_bytes_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        Settings(debug_mode_max_body_bytes=-1)
