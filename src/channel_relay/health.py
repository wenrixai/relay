"""Health/readiness logic (§13.5).

``/liveness`` reflects that the process is up. ``/readiness`` reflects whether the relay
is ready to serve traffic and reports machine-readable reasons when it is not.
"""

from __future__ import annotations

from channel_relay.config.models import RelayConfig


def readiness_reasons(config: RelayConfig | None) -> list[str]:
    """Return the reasons the relay is not ready. Empty list means ready.

    Args:
        config: the loaded relay configuration, or ``None`` if config has not loaded.
    """
    reasons: list[str] = []
    if config is None:
        reasons.append("config_not_loaded")
    return reasons
