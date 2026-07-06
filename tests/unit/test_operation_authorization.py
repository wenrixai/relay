"""Operation-name allow-list enforcement (fix #6).

A channel with `authorization.enabled=true` and a non-empty `authorization.allowed_operations`
forwards only listed operations; anything else — or an operation that cannot be determined — is
rejected 403 before the upstream is contacted. Omitted enablement or an empty list allows all.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from channel_relay.config.models import (
    AllowedOperation,
    Authorization,
    ChannelConfig,
    ChannelType,
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


def _client(upstream: _Upstream, allowed: list[str]) -> TestClient:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
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
