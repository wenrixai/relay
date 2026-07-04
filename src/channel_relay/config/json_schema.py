"""JSON Schema generated from the pydantic config models (§6.1, D13).

There is no hand-maintained ``schema.json``; external validation/publishing uses the
schema produced here.
"""

from __future__ import annotations

from typing import Any

from channel_relay.config.models import RelayConfig


def generate_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for the top-level relay configuration."""
    return RelayConfig.model_json_schema()
