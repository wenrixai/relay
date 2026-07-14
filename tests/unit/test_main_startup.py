"""Startup fail-fast for auth misconfiguration (§9.2) and startup config warnings.

Basic auth must fail *closed*: an enabled-but-unconfigured relay aborts startup rather than
serving the data-plane routes open. Mirrors the keyring fail-fast in ``test_pii_crypto``.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from loguru import logger

from channel_relay.config.models import RelayConfig
from channel_relay.main import cli, validate_auth_config, warn_unenforced_config
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


def test_startup_aborts_when_mtls_enabled_without_material() -> None:
    # Enabling mTLS without the cert/key/CA material must fail closed, not boot with the
    # data plane unauthenticated (the documented basic-off + mtls-on switch).
    settings = Settings(basic_auth_enabled=False, mtls_enabled=True)
    with pytest.raises(RuntimeError, match="mtls|mTLS|material|certificate"):
        validate_auth_config(settings)


def test_startup_ok_when_mtls_enabled_with_material(tmp_path: Any) -> None:
    ca = tmp_path / "ca.pem"
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    for f in (ca, cert, key):
        f.write_text("x", encoding="utf-8")
    settings = Settings(
        basic_auth_enabled=False,
        mtls_enabled=True,
        mtls_ca_file=str(ca),
        tls_cert_file=str(cert),
        tls_key_file=str(key),
    )
    validate_auth_config(settings)  # no raise: mTLS is enforceable


def test_cli_wires_mtls_ssl_kwargs(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    import ssl

    ca = tmp_path / "ca.pem"
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    for f in (ca, cert, key):
        f.write_text("x", encoding="utf-8")
    monkeypatch.setenv("RELAY_BASIC_AUTH_ENABLED", "false")
    monkeypatch.setenv("RELAY_MTLS_ENABLED", "true")
    monkeypatch.setenv("RELAY_MTLS_CA_FILE", str(ca))
    monkeypatch.setenv("RELAY_TLS_CERT_FILE", str(cert))
    monkeypatch.setenv("RELAY_TLS_KEY_FILE", str(key))
    captured: dict[str, Any] = {}

    def fake_run(app: str, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)
    cli()
    assert captured["ssl_certfile"] == str(cert)
    assert captured["ssl_keyfile"] == str(key)
    assert captured["ssl_ca_certs"] == str(ca)
    assert captured["ssl_cert_reqs"] == ssl.CERT_REQUIRED
    assert captured["port"] == Settings().tls_port


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
    assert captured["timeout_keep_alive"] == 75
    assert captured["proxy_headers"] is True
    assert captured["forwarded_allow_ips"] == "*"
