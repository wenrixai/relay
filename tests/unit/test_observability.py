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


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    return {metric.name for rm in data.resource_metrics for sm in rm.scope_metrics for metric in sm.metrics}


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


def test_record_request_buckets_by_status_class() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = RelayMetrics(provider.get_meter(METER_NAME))
    metrics.record_request("sabre", 200)
    metrics.record_request("sabre", 204)
    metrics.record_request("sabre", 404)
    metrics.record_request("sabre", 502)

    points = _metric_points(reader, "channel_relay_requests_total")
    by_class = {p.attributes["status_class"]: p.value for p in points}
    assert {p.attributes["channel"] for p in points} == {"sabre"}
    assert by_class == {"2xx": 2, "4xx": 1, "5xx": 1}


def test_record_upstream_error() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    metrics = RelayMetrics(provider.get_meter(METER_NAME))
    metrics.record_upstream_error("tf")
    metrics.record_upstream_error("tf")

    points = _metric_points(reader, "channel_relay_upstream_errors_total")
    assert points and points[0].value == 2
    assert points[0].attributes["channel"] == "tf"


def test_requests_total_and_http_duration_recorded_through_relay() -> None:
    reader = InMemoryMetricReader()
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
        metric_reader=reader,
    )
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200  # excluded from server metrics
        assert client.get("/channel/tf/op").status_code == 200

    # Custom per-channel counter fires with the friendly channel name and a 2xx class.
    points = _metric_points(reader, "channel_relay_requests_total")
    assert points and points[0].value == 1
    assert points[0].attributes == {"channel": "tf", "status_class": "2xx"}

    # Auto-instrumentation RED: a server-side and a client-side HTTP duration metric exist
    # (semconv metric names differ by opt-in, so match structurally).
    names = _metric_names(reader)
    server = [n for n in names if n.startswith("http.server") and "duration" in n]
    client_side = [n for n in names if n.startswith("http.client") and "duration" in n]
    assert server, f"no server duration metric in {names}"
    assert client_side, f"no client duration metric in {names}"

    # excluded_urls kept /liveness out of the server histogram.
    server_points = _metric_points(reader, server[0])
    routes = {p.attributes.get("http.route") for p in server_points}
    assert "/liveness" not in routes


def test_upstream_error_increments_metric_through_relay() -> None:
    reader = InMemoryMetricReader()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    app = create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        metric_reader=reader,
    )
    with TestClient(app) as client:
        assert client.get("/channel/tf/op").status_code == 502

    errors = _metric_points(reader, "channel_relay_upstream_errors_total")
    assert errors and errors[0].value == 1
    assert errors[0].attributes["channel"] == "tf"

    requests = _metric_points(reader, "channel_relay_requests_total")
    assert requests and requests[0].attributes == {"channel": "tf", "status_class": "5xx"}


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
