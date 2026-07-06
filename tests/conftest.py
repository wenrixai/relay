"""Shared pytest fixtures.

Network is always mocked; no test performs a real upstream call (see repo instructions).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

import httpx
import pybase64
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.xml_ops import parse_bytes
from channel_relay.proxy.errors import WENRIX_ERROR_HEADER

RelayClientFactory = Callable[[ChannelConfig, httpx.MockTransport], TestClient]
ProxyErrorAssertion = Callable[[httpx.Response, int, str, str | None], None]
XmlTexts = Callable[[bytes, str], list[str]]

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _default_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default basic auth off for suites that don't exercise it.

    The relay fails closed at startup (``validate_auth_config``) when auth is enabled
    without credentials, so any test that builds the app with default settings and enters
    the lifespan would otherwise abort. The auth/admin suites override this explicitly.
    """
    monkeypatch.setenv("RELAY_BASIC_AUTH_ENABLED", "false")


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


@pytest.fixture(name="pii_keyring")
def pii_keyring_fixture() -> Keyring:
    """A deterministic single-epoch keyring for golden PII tests."""
    key = pybase64.b64encode(bytes([7]) * 32).decode()
    return Keyring.from_json(json.dumps({"0": key}))


@pytest.fixture(name="baked_ruleset")
def baked_ruleset_fixture() -> RuleSet:
    """The baked baseline bundle actually shipped in the image."""
    baked = files("channel_relay.pii").joinpath("rules_fallback.json").read_text()
    return RuleSet.model_validate_json(baked)


@pytest.fixture(name="xml_texts")
def xml_texts_fixture() -> XmlTexts:
    """Text content of every element with the given local-name, in document order."""

    def _texts(body: bytes, local_name: str) -> list[str]:
        root = parse_bytes(body)
        return [node.text or "" for node in root.xpath(f"//*[local-name()='{local_name}']")]

    return _texts


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
