"""Configuration loader.

Reads the JSON config file and validates it against the pydantic models. On invalid
config a sanitized ``ConfigValidationError`` propagates so startup aborts with a non-zero
exit (§6.1). The original ``pydantic.ValidationError`` is never re-raised or chained: its
message embeds the offending input values (which may hold channel credentials), and an
unhandled exception ultimately reaches uvicorn's stderr logging.
``WP_*`` legacy synthesis is a later task (T4.3).
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from channel_relay.config.models import RelayConfig


class ConfigValidationError(RuntimeError):
    """Invalid relay configuration; message carries field paths and error types only."""


def _sanitize(exc: ValidationError) -> str:
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
        for error in exc.errors(include_input=False, include_url=False)
    )
    return f"invalid relay configuration: {details}"


def load_config(path: str | Path) -> RelayConfig:
    """Load and validate relay configuration from a JSON file.

    Raises:
        FileNotFoundError: if the config file does not exist.
        ConfigValidationError: if the config fails model validation (sanitized: field
            paths and error types only, never configuration values).
        json.JSONDecodeError: if the file is not valid JSON.
    """
    config_path = Path(path)
    raw = config_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    try:
        return RelayConfig.model_validate(data)
    except ValidationError as exc:
        # Log and raise the sanitized form only (never the config values, which may hold
        # secrets); `from None` keeps the value-bearing original out of the traceback chain.
        sanitized = _sanitize(exc)
        logger.bind(error_type=type(exc).__name__).error("Invalid relay configuration")
        raise ConfigValidationError(sanitized) from None
