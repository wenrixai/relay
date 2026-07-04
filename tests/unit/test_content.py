"""Tests for content handling: classification, inspection cap, pass-through (T1.8)."""

from __future__ import annotations

import gzip

import httpx
import pytest
from fastapi.testclient import TestClient

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.middleware.content import (
    ContentKind,
    body_exceeds_cap,
    classify_content,
    requires_inspection,
)


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("text/xml", ContentKind.XML),
        ("application/xml; charset=utf-8", ContentKind.XML),
        ("application/soap+xml", ContentKind.XML),
        ("application/json", ContentKind.JSON),
        ("application/ld+json", ContentKind.JSON),
        ("application/xop+xml", ContentKind.MTOM),
        ("multipart/related; type=application/xop+xml", ContentKind.MTOM),
        ("application/octet-stream", ContentKind.OPAQUE),
        (None, ContentKind.OPAQUE),
    ],
)
def test_classify_content(content_type: str | None, expected: ContentKind) -> None:
    assert classify_content(content_type) == expected


def test_requires_inspection_follows_pii_flag() -> None:
    off = ChannelConfig(name="a", type=ChannelType.TRAVELFUSION)
    on = ChannelConfig(name="b", type=ChannelType.TRAVELFUSION, pii=ChannelPII(enabled=True))
    assert requires_inspection(off) is False
    assert requires_inspection(on) is True


def test_body_exceeds_cap() -> None:
    assert body_exceeds_cap(11, 10) is True
    assert body_exceeds_cap(10, 10) is False


def _client(channel: ChannelConfig, handler: httpx.MockTransport) -> TestClient:
    config = RelayConfig(channels=[channel])
    return TestClient(create_app(config=config, http_client=httpx.AsyncClient(transport=handler)))


def test_gzip_body_passes_through_untouched() -> None:
    payload = gzip.compress(b"<Envelope>hello</Envelope>")
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)  # pii off
    with _client(channel, httpx.MockTransport(handler)) as client:
        client.post(
            "/channel/tf/op",
            content=payload,
            headers={"content-encoding": "gzip", "content-type": "application/xml"},
        )

    req = captured["req"]
    assert req.content == payload
    assert req.headers["content-encoding"] == "gzip"


def test_oversize_inspectable_body_returns_413() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        pii=ChannelPII(enabled=True),  # requires inspection
    )
    config = RelayConfig(channels=[channel])
    app = create_app(
        config=config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )
    app.state.settings.max_inspect_bytes = 8  # tiny cap
    with TestClient(app) as client:
        resp = client.post("/channel/tf/op", content=b"way-too-large-body")
    assert resp.status_code == 413
