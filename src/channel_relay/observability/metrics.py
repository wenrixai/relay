"""In-process OpenTelemetry metrics with OTLP export (§11, §11.1).

A per-app ``MeterProvider`` is built from settings; instruments live on :class:`RelayMetrics`.
The provider is kept on ``app.state`` (not set globally) so multiple app instances — e.g.
in tests — don't fight over the global provider. Collector/export failure must never crash
the relay; the periodic exporter swallows export errors.
"""

from __future__ import annotations

from collections.abc import Iterable

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import CallbackOptions, Counter, Meter, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader

from channel_relay.settings import Settings

METER_NAME = "channel_relay"


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
    return MeterProvider(metric_readers=readers)


class RelayMetrics:
    """Custom relay instruments (§11.1)."""

    def __init__(self, meter: Meter) -> None:
        self._channels_configured = 0
        self._rules_version: str | None = None
        self._upstream_timeouts: Counter = meter.create_counter(
            "upstream_timeouts_total",
            unit="1",
            description="Upstream channel timeouts (504s).",
        )
        meter.create_observable_gauge(
            "channels_configured",
            callbacks=[self._observe_channels],
            unit="1",
            description="Number of configured channels.",
        )
        meter.create_observable_gauge(
            "rule_version",
            callbacks=[self._observe_rule_version],
            unit="1",
            description="Loaded PII rules version (info-style gauge).",
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
        self._upstream_timeouts.add(1, {"channel": channel})
