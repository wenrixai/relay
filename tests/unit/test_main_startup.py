"""Startup fail-fast for auth misconfiguration (§9.2) and startup config warnings.

Basic auth must fail *closed*: an enabled-but-unconfigured relay aborts startup rather than
serving the data-plane routes open. Mirrors the keyring fail-fast in ``test_pii_crypto``.
"""

from __future__ import annotations

import inspect
import io
from typing import Any

import httpx
import pytest
from loguru import logger

from channel_relay.config.models import RelayConfig
from channel_relay.main import (
    build_http_client,
    client_limits,
    cli,
    create_app,
    validate_auth_config,
    warn_unenforced_config,
)
from channel_relay.settings import Settings


def test_startup_aborts_when_auth_enabled_without_credentials() -> None:
    settings = Settings(basic_auth_enabled=True, basic_auth_user=None, basic_auth_pass=None)
    with pytest.raises(RuntimeError, match="credential"):
        validate_auth_config(settings)


def test_startup_aborts_when_auth_enabled_with_only_user() -> None:
    settings = Settings(basic_auth_enabled=True, basic_auth_user="u", basic_auth_pass=None)
    with pytest.raises(RuntimeError, match="credential"):
        validate_auth_config(settings)


def test_startup_tolerates_auth_explicitly_disabled() -> None:
    settings = Settings(basic_auth_enabled=False, basic_auth_user=None, basic_auth_pass=None)
    validate_auth_config(settings)  # no raise


def test_startup_tolerates_auth_enabled_with_credentials() -> None:
    settings = Settings(basic_auth_enabled=True, basic_auth_user="u", basic_auth_pass="p")
    validate_auth_config(settings)  # no raise


def _capture_warnings(config: RelayConfig | None) -> str:
    sink = io.StringIO()
    sink_id = logger.add(sink, level="WARNING")
    try:
        warn_unenforced_config(config)
    finally:
        logger.remove(sink_id)
    return sink.getvalue()


def test_external_authorization_warns_at_startup() -> None:
    config = RelayConfig.model_validate(
        {
            "channels": [
                {
                    "name": "tp",
                    "type": "travelport",
                    "authorization": {"external": {"url": "https://authz.example.test"}},
                }
            ]
        }
    )
    output = _capture_warnings(config)
    assert "external" in output
    assert "NOT enforced" in output
    assert "tp" in output


def test_no_warning_without_external_authorization() -> None:
    config = RelayConfig.model_validate({"channels": [{"name": "tf", "type": "travelfusion"}]})
    assert _capture_warnings(config) == ""
    assert _capture_warnings(None) == ""


def test_debug_mode_warns_at_app_creation(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # ``create_app`` calls ``configure_logging``, which rebinds Loguru's sink to the live
    # ``sys.stderr`` (removing any sink added beforehand) — read via capsys, not logger.add.
    monkeypatch.setenv("RELAY_DEBUG_MODE", "true")
    create_app(config=RelayConfig())
    output = capsys.readouterr().err
    assert "debug_mode" in output
    assert "production" in output


def test_no_debug_mode_warning_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    create_app(config=RelayConfig())
    assert "debug_mode" not in capsys.readouterr().err


def test_cli_uvicorn_hardening_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    """cli() must pin keep-alive above the ALB idle timeout and trust proxy headers."""
    captured: dict[str, Any] = {}

    def fake_run(app: str, **kwargs: Any) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)
    cli()
    assert captured["app"] == "channel_relay.main:app"
    assert captured["server_header"] is False
    assert captured["timeout_keep_alive"] == 135
    assert captured["proxy_headers"] is True
    assert captured["forwarded_allow_ips"] == "*"
    # Fast event loop / HTTP parser pinned explicitly (fail loud, not silent asyncio/h11 fallback).
    assert captured["loop"] == "uvloop"
    assert captured["http"] == "httptools"


def test_client_limits_defaults() -> None:
    """Pool tuning defaults: raise ceilings above httpx defaults (100/20/None)."""
    limits = client_limits(Settings())
    assert limits.max_connections == 200
    assert limits.max_keepalive_connections == 50
    assert limits.keepalive_expiry == 30.0


def test_client_limits_env_overrides() -> None:
    """RELAY_* pool knobs propagate into the httpx.Limits object."""
    settings = Settings(max_connections=5, max_keepalive_connections=3, keepalive_expiry=7.5)
    limits = client_limits(settings)
    assert limits.max_connections == 5
    assert limits.max_keepalive_connections == 3
    assert limits.keepalive_expiry == 7.5


async def test_build_http_client_applies_limits_and_connect_only_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared client's transport gets the tuned limits and the connect-only retry bound

    (D12): ``retries`` is a pre-send connection-attempt retry, never a request-level retry.
    """
    captured: dict[str, Any] = {}
    real_transport = httpx.AsyncHTTPTransport

    def fake_transport(**kwargs: Any) -> httpx.AsyncHTTPTransport:
        captured.update(kwargs)
        return real_transport(**kwargs)

    monkeypatch.setattr("channel_relay.main.httpx.AsyncHTTPTransport", fake_transport)
    client = build_http_client(Settings(max_connections=11))
    try:
        assert captured["retries"] == 2
        assert captured["limits"].max_connections == 11
    finally:
        await client.aclose()


async def test_build_http_client_connect_retries_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    """``RELAY_UPSTREAM_CONNECT_RETRIES`` propagates to the transport, including disabling it."""
    captured: dict[str, Any] = {}
    real_transport = httpx.AsyncHTTPTransport

    def fake_transport(**kwargs: Any) -> httpx.AsyncHTTPTransport:
        captured.update(kwargs)
        return real_transport(**kwargs)

    monkeypatch.setattr("channel_relay.main.httpx.AsyncHTTPTransport", fake_transport)
    client = build_http_client(Settings(upstream_connect_retries=0))
    try:
        assert captured["retries"] == 0
    finally:
        await client.aclose()


async def test_build_http_client_always_verifies_tls() -> None:
    client = build_http_client(Settings())
    try:
        assert (
            client._transport_for_url(httpx.URL("https://example.test"))._pool._ssl_context.verify_mode.name
            != "CERT_NONE"
        )  # noqa: SLF001
    finally:
        await client.aclose()


def test_build_http_client_takes_no_verify_argument() -> None:
    """No opt-out at any level: the non-verifying path must not be one keyword away."""
    assert "verify" not in inspect.signature(build_http_client).parameters
