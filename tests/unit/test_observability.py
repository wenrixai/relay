"""Tests for observability: metrics and access log (T1.11)."""

from __future__ import annotations

import io
import json
from typing import Any

import httpx
from fastapi.testclient import TestClient
from loguru import logger
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from channel_relay import __version__
from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.middleware.access_log import log_access
from channel_relay.observability.metrics import METER_NAME, SERVICE_NAME, RelayMetrics


def _metric_points(reader: InMemoryMetricReader, name: str) -> list[Any]:
    data = reader.get_metrics_data()
    points: list[Any] = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return points


def test_relay_metrics_counter_and_gauge() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = RelayMetrics(provider.get_meter(METER_NAME))
    metrics.set_channels_configured(3)
    metrics.record_upstream_timeout("tf")
    metrics.record_upstream_timeout("tf")
    metrics.record_pii_rule_path_error("tf", "tf.bad-prefix")

    timeouts = _metric_points(reader, "channel_relay_upstream_timeouts_total")
    assert timeouts and timeouts[0].value == 2
    assert timeouts[0].attributes["channel"] == "tf"

    gauge = _metric_points(reader, "channel_relay_channels_configured")
    assert gauge and gauge[0].value == 3

    path_errors = _metric_points(reader, "channel_relay_pii_rule_path_errors_total")
    assert path_errors and path_errors[0].value == 1
    assert path_errors[0].attributes == {"channel": "tf", "rule_id": "tf.bad-prefix"}


def test_app_meter_provider_has_otel_service_resource() -> None:
    reader = InMemoryMetricReader()
    app = create_app(metric_reader=reader)
    app.state.metrics.set_channels_configured(1)

    metrics_data = reader.get_metrics_data()
    resource = metrics_data.resource_metrics[0].resource

    assert resource.attributes["service.name"] == SERVICE_NAME
    assert resource.attributes["service.version"] == __version__


def test_channels_configured_set_on_startup() -> None:
    reader = InMemoryMetricReader()
    config = RelayConfig(
        channels=[
            ChannelConfig(name="a", type=ChannelType.TRAVELFUSION),
            ChannelConfig(name="b", type=ChannelType.BA_NDC_DIRECT),
        ]
    )
    handler = httpx.MockTransport(lambda r: httpx.Response(200))
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=handler),
        metric_reader=reader,
    )
    with TestClient(app):
        pass  # lifespan runs, sets the gauge
    gauge = _metric_points(reader, "channel_relay_channels_configured")
    assert gauge and gauge[0].value == 2


def test_upstream_timeout_increments_metric() -> None:
    reader = InMemoryMetricReader()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        metric_reader=reader,
    )
    with TestClient(app) as client:
        assert client.get("/channel/tf/op").status_code == 504

    points = _metric_points(reader, "channel_relay_upstream_timeouts_total")
    assert points and points[0].value == 1
    assert points[0].attributes["channel"] == "tf"


def test_access_log_fields() -> None:
    sink = io.StringIO()
    sink_id = logger.add(sink, serialize=True, level="INFO")
    try:
        log_access(channel="tf", method="POST", path="op", status=200, latency_ms=12.5, trace_id="t1")
    finally:
        logger.remove(sink_id)
    record = json.loads(sink.getvalue().strip())
    extra = record["record"]["extra"]
    assert extra["channel"] == "tf"
    assert extra["status"] == 200
    assert extra["trace_id"] == "t1"
    assert "hostname" in extra
    assert "latency_ms" in extra
    assert "body" not in extra
