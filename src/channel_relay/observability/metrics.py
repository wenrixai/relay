"""In-process OpenTelemetry metrics with OTLP export (§11, §11.1).

A per-app ``MeterProvider`` is built from settings; instruments live on :class:`RelayMetrics`.
The provider is kept on ``app.state`` (not set globally) so multiple app instances — e.g.
in tests — don't fight over the global provider. Collector/export failure must never crash
the relay; the periodic exporter swallows export errors.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import CallbackOptions, Counter as OtelCounter, Meter, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME as OTEL_SERVICE_NAME
from opentelemetry.sdk.resources import SERVICE_VERSION, Resource

from channel_relay import __version__
from channel_relay.settings import Settings

METER_NAME = "channel_relay"
METRIC_PREFIX = "channel_relay_"
SERVICE_NAME = "wenrix-channel-relay"


def _metric_name(name: str) -> str:
    return f"{METRIC_PREFIX}{name}"


@dataclass
class _MetricTotals:
    """In-process totals mirroring the write-only OTel counters."""

    upstream_timeouts: dict[str, int] = field(default_factory=dict)
    pii_redacted: dict[str, dict[str, int]] = field(default_factory=dict)
    pii_decrypted: dict[str, int] = field(default_factory=dict)
    xml_parse_errors: dict[str, dict[str, int]] = field(default_factory=dict)
    operations_denied: dict[str, int] = field(default_factory=dict)
    uncovered_operations: dict[str, dict[str, int]] = field(default_factory=dict)
    rule_namespace_misses: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def increment(values: dict[str, int], key: str, count: int = 1) -> None:
        """Increment a flat counter mapping."""
        values[key] = values.get(key, 0) + count

    @staticmethod
    def increment_nested(values: dict[str, dict[str, int]], key: str, nested_key: str, count: int) -> None:
        """Increment a nested counter mapping."""
        nested_values = values.setdefault(key, {})
        nested_values[nested_key] = nested_values.get(nested_key, 0) + count

    def snapshot(self, *, channels_configured: int, rules_version: str | None) -> dict[str, object]:
        """Return stable JSON-compatible totals."""
        return {
            "channels_configured": channels_configured,
            "rules_version": rules_version,
            "upstream_timeouts_total": dict(sorted(self.upstream_timeouts.items())),
            "pii_fields_redacted_total": {
                channel: dict(sorted(counts.items())) for channel, counts in sorted(self.pii_redacted.items())
            },
            "pii_fields_decrypted_total": dict(sorted(self.pii_decrypted.items())),
            "xml_parse_errors_total": {
                channel: dict(sorted(counts.items())) for channel, counts in sorted(self.xml_parse_errors.items())
            },
            "operations_denied_total": dict(sorted(self.operations_denied.items())),
            "pii_uncovered_operation_total": {
                channel: dict(sorted(counts.items())) for channel, counts in sorted(self.uncovered_operations.items())
            },
            "rule_namespace_miss_total": dict(sorted(self.rule_namespace_misses.items())),
        }


def build_meter_provider(
    settings: Settings,
    reader: MetricReader | None = None,
) -> MeterProvider:
    """Build a MeterProvider.

    Tests inject an in-memory ``reader``. Production attaches an OTLP periodic exporter only
    when metrics are enabled *and* an endpoint is configured — so a relay with no collector
    (and the test suite) never spawns an exporter that retries against a dead endpoint.
    """
    readers: list[MetricReader] = []
    if reader is not None:
        readers.append(reader)
    elif settings.telemetry_metrics_enabled and settings.otlp_endpoint:
        exporter = OTLPMetricExporter(endpoint=settings.otlp_endpoint)
        readers.append(PeriodicExportingMetricReader(exporter))
    resource = Resource.create(
        {
            OTEL_SERVICE_NAME: SERVICE_NAME,
            SERVICE_VERSION: __version__,
        }
    )
    return MeterProvider(metric_readers=readers, resource=resource)


class RelayMetrics:  # pylint: disable=too-many-instance-attributes
    """Custom relay instruments (§11.1); one attribute per instrument, so the count is expected."""

    def __init__(self, meter: Meter) -> None:
        self._channels_configured = 0
        self._rules_version: str | None = None
        self._totals = _MetricTotals()
        self._upstream_timeouts: OtelCounter = meter.create_counter(
            _metric_name("upstream_timeouts_total"),
            unit="1",
            description="Upstream channel timeouts (504s).",
        )
        meter.create_observable_gauge(
            _metric_name("channels_configured"),
            callbacks=[self._observe_channels],
            unit="1",
            description="Number of configured channels.",
        )
        meter.create_observable_gauge(
            _metric_name("rule_version"),
            callbacks=[self._observe_rule_version],
            unit="1",
            description="Loaded PII rules version (info-style gauge).",
        )
        self._pii_redacted: OtelCounter = meter.create_counter(
            _metric_name("pii_fields_redacted_total"),
            unit="1",
            description="PII fields actioned on responses.",
        )
        self._pii_decrypted: OtelCounter = meter.create_counter(
            _metric_name("pii_fields_decrypted_total"),
            unit="1",
            description="ENC_ tokens de-anonymized on requests.",
        )
        self._xml_parse_errors: OtelCounter = meter.create_counter(
            _metric_name("xml_parse_errors_total"),
            unit="1",
            description="Hardened XML parse/structure rejections.",
        )
        self._operations_denied: OtelCounter = meter.create_counter(
            _metric_name("operations_denied_total"),
            unit="1",
            description="Requests rejected by operation authorization (403).",
        )
        self._uncovered_operations: OtelCounter = meter.create_counter(
            _metric_name("pii_uncovered_operation_total"),
            unit="1",
            description="PII-enabled responses whose operation matched no redaction rules (forwarded).",
        )
        self._rule_namespace_misses: OtelCounter = meter.create_counter(
            _metric_name("rule_namespace_miss_total"),
            unit="1",
            description="Rule paths that resolved to a no-match because a namespace prefix was undeclared.",
        )

    def _observe_channels(
        self,
        options: CallbackOptions,  # pylint: disable=unused-argument
    ) -> Iterable[Observation]:
        # ``options`` is required by the OTel observable-gauge callback signature.
        return [Observation(self._channels_configured)]

    def _observe_rule_version(
        self,
        options: CallbackOptions,  # pylint: disable=unused-argument
    ) -> Iterable[Observation]:
        # Info-style gauge: constant 1 with the version as an attribute (§11.1).
        if self._rules_version is None:
            return []
        return [Observation(1, {"rules_version": self._rules_version})]

    def set_rule_version(self, version: str) -> None:
        """Report the loaded ``rules_version`` via the ``rule_version`` gauge."""
        self._rules_version = version

    def set_channels_configured(self, count: int) -> None:
        """Set the gauge value reported for configured channels."""
        self._channels_configured = count

    def record_upstream_timeout(self, channel: str) -> None:
        """Increment the upstream-timeout counter for a channel."""
        self._totals.increment(self._totals.upstream_timeouts, channel)
        self._upstream_timeouts.add(1, {"channel": channel})

    def record_pii_redacted(self, channel: str, counts: Mapping[str, int]) -> None:
        """Record redacted-field counts per ``pii_type`` (label values, never field data)."""
        for pii_type, count in counts.items():
            if count:
                self._totals.increment_nested(self._totals.pii_redacted, channel, pii_type, count)
                self._pii_redacted.add(count, {"channel": channel, "pii_type": pii_type})

    def record_pii_decrypted(self, channel: str, count: int) -> None:
        """Record how many tokens were de-anonymized on a request."""
        if count:
            self._totals.increment(self._totals.pii_decrypted, channel, count)
            self._pii_decrypted.add(count, {"channel": channel})

    def record_xml_parse_error(self, channel: str, kind: str) -> None:
        """Record a hardened-parser rejection with its stable ``kind``."""
        self._totals.increment_nested(self._totals.xml_parse_errors, channel, kind, 1)
        self._xml_parse_errors.add(1, {"channel": channel, "kind": kind})

    def record_operation_denied(self, channel: str) -> None:
        """Record a request rejected by operation authorization (403)."""
        self._totals.increment(self._totals.operations_denied, channel)
        self._operations_denied.add(1, {"channel": channel})

    def record_uncovered_operation(self, channel: str, operation: str) -> None:
        """Record a PII-enabled response forwarded with no matching redaction rules."""
        self._totals.increment_nested(self._totals.uncovered_operations, channel, operation, 1)
        self._uncovered_operations.add(1, {"channel": channel, "operation": operation})

    def record_rule_namespace_miss(self, channel: str) -> None:
        """Record a rule path that matched nothing due to an undeclared namespace prefix."""
        self._totals.increment(self._totals.rule_namespace_misses, channel)
        self._rule_namespace_misses.add(1, {"channel": channel})

    def snapshot(self) -> dict[str, object]:
        """Return safe in-process metric totals for admin diagnostics."""
        return self._totals.snapshot(
            channels_configured=self._channels_configured,
            rules_version=self._rules_version,
        )
