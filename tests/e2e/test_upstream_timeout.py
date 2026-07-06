"""Item 5 — an upstream timeout returns 504 text/html with ``X-Wenrix-Error: upstream_timeout`` and
no ``Server`` header, and increments the ``upstream_timeouts_total`` counter.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from tests.e2e.conftest import GDS_PARAMS, SABRE, E2EClientFactory, Gds, RecordingUpstream, make_channel

pytestmark = pytest.mark.e2e

_TIMEOUT_COUNTER = "channel_relay_upstream_timeouts_total"


def _counter_for_channel(reader: InMemoryMetricReader, name: str, channel: str) -> float:
    """Sum the values of a counter's data points for one channel (mirrors test_observability)."""
    points: list[Any] = []
    data = reader.get_metrics_data()
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return sum(p.value for p in points if p.attributes.get("channel") == channel)


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_read_timeout_returns_504(gds: Gds, e2e_client: E2EClientFactory) -> None:
    upstream = RecordingUpstream(raise_exc=httpx.ReadTimeout("slow upstream"))
    channel = make_channel(gds, credentialed=True, pii_enabled=True)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post(
            f"/channel/{gds.name}/op", content=gds.request_body(), headers={"content-type": "text/xml"}
        )

    assert response.status_code == 504
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-wenrix-error"] == "upstream_timeout"
    assert "server" not in {k.lower() for k in response.headers}
    assert upstream.bodies == []


def test_connect_timeout_also_504(e2e_client: E2EClientFactory) -> None:
    """ConnectTimeout is a TimeoutException subclass, caught before the generic HTTPError branch."""
    upstream = RecordingUpstream(raise_exc=httpx.ConnectTimeout("no route"))
    channel = make_channel(SABRE, credentialed=True, pii_enabled=True)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post("/channel/sabre/op", content=SABRE.request_body(), headers={"content-type": "text/xml"})

    assert response.status_code == 504
    assert response.headers["x-wenrix-error"] == "upstream_timeout"


def test_timeout_increments_metric(e2e_client: E2EClientFactory) -> None:
    reader = InMemoryMetricReader()
    upstream = RecordingUpstream(raise_exc=httpx.ReadTimeout("slow upstream"))
    channel = make_channel(SABRE, credentialed=True, pii_enabled=True)
    client: TestClient = e2e_client(channel, upstream, metric_reader=reader)
    with client:
        before = _counter_for_channel(reader, _TIMEOUT_COUNTER, "sabre")
        client.post("/channel/sabre/op", content=SABRE.request_body(), headers={"content-type": "text/xml"})
        after = _counter_for_channel(reader, _TIMEOUT_COUNTER, "sabre")

    assert after - before == 1
