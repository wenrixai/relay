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
