"""Tests for OpenTelemetry tracing (§11): off by default, span model on the forward path."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from channel_relay import __version__
from channel_relay.config.models import ChannelConfig, ChannelType, RelayConfig
from channel_relay.main import create_app
from channel_relay.observability.metrics import SERVICE_NAME
from channel_relay.observability.tracing import build_tracer_provider, tracer_from_provider
from channel_relay.settings import Settings


def _span_names(exporter: InMemorySpanExporter) -> set[str]:
    return {span.name for span in exporter.get_finished_spans()}


def _span(exporter: InMemorySpanExporter, name: str) -> ReadableSpan:
    matches = [span for span in exporter.get_finished_spans() if span.name == name]
    assert matches, f"span {name!r} not exported"
    return matches[0]


def _make_app(exporter: InMemorySpanExporter, transport: httpx.MockTransport) -> FastAPI:
    config = RelayConfig(channels=[ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)])
    return create_app(
        config=config,
        http_client=httpx.AsyncClient(transport=transport),
        span_processor=SimpleSpanProcessor(exporter),
    )


def test_tracer_provider_resource_has_service_identity() -> None:
    provider = build_tracer_provider(Settings())
    assert provider.resource.attributes["service.name"] == SERVICE_NAME
    assert provider.resource.attributes["service.version"] == __version__


def test_tracing_disabled_by_default() -> None:
    assert Settings().telemetry_traces_enabled is False
    app = create_app()
    assert app.state.tracer_provider is None


def test_noop_tracer_when_disabled_records_nothing() -> None:
    tracer = tracer_from_provider(None)
    with tracer.start_as_current_span("relay.forward") as span:
        assert not span.is_recording()


def test_forward_path_spans_recorded_through_relay() -> None:
    exporter = InMemorySpanExporter()
    app = _make_app(exporter, httpx.MockTransport(lambda r: httpx.Response(200)))
    with TestClient(app) as client:
        assert client.get("/liveness").status_code == 200  # excluded from tracing
        response = client.get("/channel/tf/op", headers={"x-wenrix-trace-id": "t-42"})
        assert response.status_code == 200

    names = _span_names(exporter)
    assert {"relay.forward", "relay.upstream"} <= names
    assert not any("liveness" in name for name in names)

    forward_span = _span(exporter, "relay.forward")
    assert forward_span.attributes is not None
    assert forward_span.attributes["wenrix.channel"] == "tf"
    assert forward_span.attributes["wenrix.trace_id"] == "t-42"
    assert forward_span.attributes["http.response.status_code"] == 200

    # relay.upstream nests under relay.forward; the auto-instrumented httpx CLIENT span
    # nests under relay.upstream; a FastAPI SERVER span exists above it all.
    upstream_span = _span(exporter, "relay.upstream")
    assert upstream_span.parent is not None
    assert upstream_span.parent.span_id == forward_span.context.span_id
    spans = exporter.get_finished_spans()
    assert any(
        span.kind is SpanKind.CLIENT
        and span.parent is not None
        and span.parent.span_id == upstream_span.context.span_id
        for span in spans
    )
    assert any(span.kind is SpanKind.SERVER for span in spans)


def test_span_attributes_never_carry_bodies() -> None:
    exporter = InMemorySpanExporter()
    body = b"<Request><Secret>ENC_abc</Secret></Request>"
    app = _make_app(exporter, httpx.MockTransport(lambda r: httpx.Response(200)))
    with TestClient(app) as client:
        assert client.post("/channel/tf/op", content=body).status_code == 200
    for span in exporter.get_finished_spans():
        for value in (span.attributes or {}).values():
            assert "ENC_" not in str(value)
            assert "Secret" not in str(value)


def test_upstream_timeout_marks_span_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    exporter = InMemorySpanExporter()
    app = _make_app(exporter, httpx.MockTransport(handler))
    with TestClient(app) as client:
        assert client.get("/channel/tf/op").status_code == 504

    upstream_span = _span(exporter, "relay.upstream")
    assert upstream_span.status.status_code is StatusCode.ERROR
