"""PII metric instruments and their wiring (T2.7, §11.1)."""

from __future__ import annotations

from typing import Any

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from channel_relay.observability.metrics import METER_NAME, RelayMetrics


def _metric_points(reader: InMemoryMetricReader, name: str) -> list[Any]:
    data = reader.get_metrics_data()
    points: list[Any] = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return points


def _build() -> tuple[InMemoryMetricReader, RelayMetrics]:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return reader, RelayMetrics(provider.get_meter(METER_NAME))


def test_pii_fields_redacted_by_type() -> None:
    reader, metrics = _build()
    metrics.record_pii_redacted("mock", {"person": 2, "email": 1})
    points = _metric_points(reader, "pii_fields_redacted_total")
    by_type = {p.attributes["pii_type"]: p.value for p in points}
    assert by_type == {"person": 2, "email": 1}
    assert all(p.attributes["channel"] == "mock" for p in points)


def test_pii_fields_decrypted() -> None:
    reader, metrics = _build()
    metrics.record_pii_decrypted("mock", 3)
    points = _metric_points(reader, "pii_fields_decrypted_total")
    assert points and points[0].value == 3
    assert points[0].attributes["channel"] == "mock"


def test_pii_decrypted_zero_not_recorded() -> None:
    reader, metrics = _build()
    metrics.record_pii_decrypted("mock", 0)
    assert not _metric_points(reader, "pii_fields_decrypted_total")


def test_xml_parse_errors_by_kind() -> None:
    reader, metrics = _build()
    metrics.record_xml_parse_error("mock", "doctype")
    metrics.record_xml_parse_error("mock", "doctype")
    metrics.record_xml_parse_error("mock", "malformed")
    points = _metric_points(reader, "xml_parse_errors_total")
    by_kind = {p.attributes["kind"]: p.value for p in points}
    assert by_kind == {"doctype": 2, "malformed": 1}


def test_rule_version_info_gauge() -> None:
    reader, metrics = _build()
    metrics.set_rule_version("2026-07-01")
    points = _metric_points(reader, "rule_version")
    assert points and points[0].value == 1
    assert points[0].attributes["rules_version"] == "2026-07-01"


def test_rule_version_absent_until_set() -> None:
    reader, _ = _build()
    assert not _metric_points(reader, "rule_version")
