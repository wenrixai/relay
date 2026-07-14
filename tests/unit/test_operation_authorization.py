"""Operation-name allow-list enforcement (fix #6).

A channel with `authorization.enabled=true` and a non-empty `authorization.allowed_operations`
forwards only listed operations; anything else — or an operation that cannot be determined — is
rejected 403 before the upstream is contacted. Omitted enablement or an empty list allows all.
"""

from __future__ import annotations

from typing import cast

import httpx
import pybase64
from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_relay.config.models import (
    AllowedOperation,
    Authorization,
    ChannelConfig,
    ChannelType,
    Credentials,
    RelayConfig,
)
from channel_relay.main import create_app

# Travelfusion parse_operation = first non-GeneralInfoItemList child local-name.
_ALLOWED_BODY = b"<Ping><CheckFareRequest/></Ping>"
_DISALLOWED_BODY = b"<Ping><BookRequest/></Ping>"


class _Upstream:
    def __init__(self) -> None:
        self.calls = 0

    def handler(self, _request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(200, content=b"<ok/>", headers={"content-type": "application/xml"})


def _client(upstream: _Upstream, allowed: list[str], *, credentials: Credentials | None = None) -> TestClient:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials=credentials or Credentials(),
        authorization=Authorization(
            enabled=bool(allowed),
            allowed_operations=[AllowedOperation(operation=op, version="*") for op in allowed],
        ),
    )
    return TestClient(
        create_app(
            config=RelayConfig(channels=[channel]),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)),
        )
    )


def _basic(user: str, password: str) -> str:
    token = pybase64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def test_allowed_operation_is_forwarded() -> None:
    upstream = _Upstream()
    with _client(upstream, ["CheckFareRequest"]) as client:
        resp = client.post("/channel/tf/op", content=_ALLOWED_BODY, headers={"content-type": "application/xml"})
    assert resp.status_code == 200
    assert upstream.calls == 1


def test_disallowed_operation_rejected_before_upstream() -> None:
    upstream = _Upstream()
    with _client(upstream, ["CheckFareRequest"]) as client:
        resp = client.post(
            "/channel/tf/op",
            content=_DISALLOWED_BODY,
            headers={"content-type": "application/xml", "x-wenrix-trace-id": "t9"},
        )
    assert resp.status_code == 403
    assert resp.headers["X-Wenrix-Error"] == "operation_not_allowed"
    assert resp.json()["trace_id"] == "t9"
    assert upstream.calls == 0  # never contacted


def test_malformed_xml_is_rejected_before_upstream() -> None:
    upstream = _Upstream()
    with _client(upstream, ["CheckFareRequest"]) as client:
        resp = client.post(
            "/channel/tf/op",
            content=b"<Ping><CheckFareRequest>",
            headers={"content-type": "application/xml", "x-wenrix-trace-id": "malformed-trace"},
        )

    assert resp.status_code == 502
    assert resp.headers["X-Wenrix-Error"] == "xml_parse_error"
    assert resp.json() == {
        "error": "bad_gateway",
        "reason": "xml_parse_error",
        "detail": "request body is not parseable XML",
        "trace_id": "malformed-trace",
    }
    assert upstream.calls == 0


def test_oversized_xml_is_rejected_before_upstream() -> None:
    upstream = _Upstream()
    client = _client(upstream, ["CheckFareRequest"])
    app = cast(FastAPI, client.app)
    app.state.settings.max_inspect_bytes = 16

    with client:
        resp = client.post(
            "/channel/tf/op",
            content=_ALLOWED_BODY,
            headers={"content-type": "application/xml"},
        )

    assert resp.status_code == 413
    assert resp.headers["X-Wenrix-Error"] == "payload_too_large"
    assert resp.json() == {"error": "payload_too_large"}
    assert upstream.calls == 0


def test_disallowed_operation_is_rejected_before_credential_swap() -> None:
    upstream = _Upstream()
    credentials = Credentials(enabled=True, login_id="relay-login", xml_login_id="relay-xml")

    # The denied operation intentionally omits the login nodes required by credential swap. If
    # swap ran first, this would fail with credential_swap_failed instead of the authorization 403.
    with _client(upstream, ["CheckFareRequest"], credentials=credentials) as client:
        resp = client.post(
            "/channel/tf/op",
            content=_DISALLOWED_BODY,
            headers={"content-type": "application/xml"},
        )

    assert resp.status_code == 403
    assert resp.headers["X-Wenrix-Error"] == "operation_not_allowed"
    assert upstream.calls == 0


def test_denied_operation_is_visible_in_admin_statistics() -> None:
    upstream = _Upstream()
    client = _client(upstream, ["CheckFareRequest"])
    app = cast(FastAPI, client.app)

    with client:
        denied = client.post(
            "/channel/tf/op",
            content=_DISALLOWED_BODY,
            headers={"content-type": "application/xml"},
        )
        app.state.settings.basic_auth_enabled = True
        app.state.settings.basic_auth_user = "admin"
        app.state.settings.basic_auth_pass = "secret-pass"
        diagnostics = client.get(
            "/admin/flare",
            headers={"authorization": _basic("admin", "secret-pass")},
        )

    assert denied.status_code == 403
    assert diagnostics.status_code == 200
    assert diagnostics.json()["statistics"]["operations_denied_total"] == {"tf": 1}
    assert upstream.calls == 0


def test_empty_list_allows_all() -> None:
    upstream = _Upstream()
    with _client(upstream, []) as client:
        resp = client.post("/channel/tf/op", content=_DISALLOWED_BODY, headers={"content-type": "application/xml"})
    assert resp.status_code == 200
    assert upstream.calls == 1


def test_allowed_operations_without_enabled_allows_all() -> None:
    upstream = _Upstream()
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        authorization=Authorization(
            allowed_operations=[AllowedOperation(operation="CheckFareRequest", version="*")],
        ),
    )
    with TestClient(
        create_app(
            config=RelayConfig(channels=[channel]),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)),
        )
    ) as client:
        resp = client.post("/channel/tf/op", content=_DISALLOWED_BODY, headers={"content-type": "application/xml"})
    assert resp.status_code == 200
    assert upstream.calls == 1


def test_non_xml_body_with_configured_list_is_rejected() -> None:
    upstream = _Upstream()
    with _client(upstream, ["CheckFareRequest"]) as client:
        resp = client.post("/channel/tf/op", content=b"not xml", headers={"content-type": "application/json"})
    assert resp.status_code == 403
    assert resp.headers["X-Wenrix-Error"] == "operation_not_allowed"
    assert upstream.calls == 0
