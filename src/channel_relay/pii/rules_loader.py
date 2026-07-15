"""Rules delivery: local-only, loaded once at startup, never polled (§8.8, D7).

Rules always load from the baked bundle shipped in the image; there is no runtime fetch. An
invalid baked bundle aborts startup when PII is enabled (fail closed); without PII it degrades to
"no rules loaded".
"""

from __future__ import annotations

from importlib import resources

from loguru import logger
from pydantic import ValidationError

from channel_relay.pii.rules import RuleSet

_BAKED_RESOURCE = "rules_fallback.json"


def _read_baked_text() -> str:
    return (resources.files("channel_relay.pii") / _BAKED_RESOURCE).read_text(encoding="utf-8")


def load_baked_rules() -> RuleSet:
    """Parse the baked fallback bundle shipped in the image.

    Raises:
        pydantic.ValidationError | ValueError: the bundle is invalid (a build defect).
    """
    return RuleSet.model_validate_json(_read_baked_text())


async def load_rules(*, pii_required: bool) -> RuleSet | None:
    """Load the active ruleset from the baked bundle.

    Args:
        pii_required: whether any channel has PII enabled; governs fail-closed behavior.

    Raises:
        RuntimeError: no valid ruleset is available while PII is enabled.
    """
    try:
        baked = load_baked_rules()
    except (ValidationError, ValueError, OSError) as exc:
        if pii_required:
            msg = "baked rules bundle is invalid and PII is enabled"
            raise RuntimeError(msg) from exc
        logger.bind(error_type=type(exc).__name__).warning("Baked rules bundle invalid; no rules loaded")
        return None
    logger.bind(rules_version=baked.rules_version).info("Rules loaded from baked bundle")
    return baked
