"""Shared pytest fixtures.

Network is always mocked; no test performs a real upstream call (see repo instructions).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.proxy.errors import WENRIX_ERROR_HEADER

RelayClientFactory = Callable[[ChannelConfig, httpx.MockTransport], TestClient]
ProxyErrorAssertion = Callable[[httpx.Response, int, str, str | None], None]


@pytest.fixture
def client() -> TestClient:
    """A TestClient bound to a fresh app instance with an empty (ready) config."""
    return TestClient(create_app(config=RelayConfig()))


@pytest.fixture
def relay_client_factory() -> RelayClientFactory:
    """Create a TestClient for a single configured upstream channel."""

    def _factory(channel: ChannelConfig, transport: httpx.MockTransport) -> TestClient:
        config = RelayConfig(channels=[channel])
        http_client = httpx.AsyncClient(transport=transport)
        return TestClient(create_app(config=config, http_client=http_client))

    return _factory


@pytest.fixture
def travelfusion_client(relay_client_factory: RelayClientFactory) -> Callable[[httpx.MockTransport], TestClient]:
    """Create a TestClient for the default TravelFusion channel."""

    def _factory(transport: httpx.MockTransport) -> TestClient:
        return relay_client_factory(ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION), transport)

    return _factory


@pytest.fixture
def unreachable_transport() -> httpx.MockTransport:
    """Fail the test if a request reaches the mocked upstream."""

    def _handler(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"unexpected upstream request: {request.method} {request.url}")

    return httpx.MockTransport(_handler)


@pytest.fixture
def assert_proxy_error() -> ProxyErrorAssertion:
    """Assert the shared proxy error response contract."""

    def _assert(resp: httpx.Response, status_code: int, reason: str, trace_id: str | None = None) -> None:
        assert resp.status_code == status_code
        assert resp.headers[WENRIX_ERROR_HEADER] == reason
        body = resp.json()
        assert body["reason"] == reason
        if trace_id is not None:
            assert body["trace_id"] == trace_id

    return _assert
