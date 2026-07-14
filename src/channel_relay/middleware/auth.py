"""Client authentication: HTTP basic auth (default, §9.2).

Basic auth is enforced on served channel/admin routes when it is *active* — enabled and
with credentials configured. Comparison is constant-time. Health probes are always open.
mTLS is opt-in and handled at the server layer (later).
"""

from __future__ import annotations

import binascii
import hmac
from pathlib import Path

import pybase64
from fastapi import HTTPException, Request

from channel_relay.settings import Settings

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Basic realm="wenrix-relay"'}


def auth_active(settings: Settings) -> bool:
    """True when basic auth is enabled *and* credentials are configured.

    Drives ``verify_basic_auth``: when basic auth is enabled but credentials are unconfigured
    the relay cannot enforce it and startup aborts (see ``validate_auth_config``). This concerns
    only the basic-auth mechanism; mTLS enforcement is a separate transport-layer concern.
    """
    return bool(
        settings.basic_auth_enabled and settings.basic_auth_user is not None and settings.basic_auth_pass is not None
    )


def mtls_material_complete(settings: Settings) -> bool:
    """True when mTLS is enabled and all required material (server cert/key + CA) exists.

    mTLS is enforced at the TLS handshake (uvicorn ``ssl_cert_reqs=CERT_REQUIRED``); this
    predicate reports whether that enforcement can actually be wired, so the startup guard and
    diagnostics never treat the mere ``mtls_enabled`` flag as if it protected the routes.
    """
    if not settings.mtls_enabled:
        return False
    paths = (settings.tls_cert_file, settings.tls_key_file, settings.mtls_ca_file)
    return all(p is not None and Path(p).exists() for p in paths)


def client_auth_enforced(settings: Settings) -> bool:
    """True when at least one client-auth mechanism is actively enforced (basic or mTLS)."""
    return auth_active(settings) or mtls_material_complete(settings)


def parse_basic_credentials(header: str | None) -> tuple[str, str] | None:
    """Parse ``Authorization: Basic <base64(user:pass)>``; ``None`` if absent/malformed."""
    if not header:
        return None
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = pybase64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    user, sep, password = decoded.partition(":")
    if not sep:
        return None
    return user, password


def credentials_valid(user: str, password: str, settings: Settings) -> bool:
    """Constant-time comparison of supplied credentials against configuration."""
    expected_user = settings.basic_auth_user or ""
    expected_pass = settings.basic_auth_pass or ""
    user_ok = hmac.compare_digest(user, expected_user)
    pass_ok = hmac.compare_digest(password, expected_pass)
    return user_ok and pass_ok


def verify_basic_auth(request: Request) -> None:
    """FastAPI dependency: enforce basic auth on served routes when active."""
    settings: Settings = request.app.state.settings
    if not auth_active(settings):
        return
    creds = parse_basic_credentials(request.headers.get("authorization"))
    if creds is None or not credentials_valid(creds[0], creds[1], settings):
        raise HTTPException(status_code=401, detail="unauthorized", headers=_UNAUTHORIZED_HEADERS)


def verify_admin_basic_auth(request: Request) -> None:
    """FastAPI dependency: fail-closed basic auth for admin diagnostics routes."""
    settings: Settings = request.app.state.settings
    creds = parse_basic_credentials(request.headers.get("authorization"))
    if not auth_active(settings) or creds is None or not credentials_valid(creds[0], creds[1], settings):
        raise HTTPException(status_code=401, detail="unauthorized", headers=_UNAUTHORIZED_HEADERS)
