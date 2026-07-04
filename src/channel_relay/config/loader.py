"""Configuration loader.

Reads the JSON config file and validates it against the pydantic models. On invalid
config the ``ValidationError`` propagates so startup aborts with a non-zero exit (§6.1).
``WP_*`` legacy synthesis is a later task (T4.3); a hook is left for it.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from channel_relay.config.models import RelayConfig


def load_config(path: str | Path) -> RelayConfig:
    """Load and validate relay configuration from a JSON file.

    Raises:
        FileNotFoundError: if the config file does not exist.
        pydantic.ValidationError: if the config fails model validation.
        json.JSONDecodeError: if the file is not valid JSON.
    """
    config_path = Path(path)
    raw = config_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    try:
        return RelayConfig.model_validate(data)
    except Exception as exc:  # re-raise after logging to abort startup
        # Log the validation error (never the config values, which may hold secrets).
        logger.error("Invalid relay configuration: {}", type(exc).__name__)
        raise
