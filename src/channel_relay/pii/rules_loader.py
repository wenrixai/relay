"""Rules delivery: one startup fetch, baked fallback, never polled (§8.8, D7).

The Wenrix rules-API contract is a documented assumption pending O3: ``GET`` on the
configured URL returning the §8.1 JSON document. One attempt with a short timeout and no
retries (D12); any failure — network, HTTP status, malformed body, incompatible schema —
falls back to the bundle baked into the image. An invalid baked bundle aborts startup
when PII is enabled (fail closed); without PII it degrades to "no rules loaded".
"""

from __future__ import annotations

from importlib import resources

import httpx
from loguru import logger
from pydantic import ValidationError

from channel_relay.pii.rules import RuleSet

_FETCH_TIMEOUT_SECONDS = 5.0
_BAKED_RESOURCE = "rules_fallback.json"


def _read_baked_text() -> str:
    return (resources.files("channel_relay.pii") / _BAKED_RESOURCE).read_text(encoding="utf-8")


def load_baked_rules() -> RuleSet:
    """Parse the baked fallback bundle shipped in the image.

    Raises:
        pydantic.ValidationError | ValueError: the bundle is invalid (a build defect).
    """
    return RuleSet.model_validate_json(_read_baked_text())


async def _fetch_rules(client: httpx.AsyncClient, url: str) -> RuleSet:
    response = await client.get(url, timeout=_FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    return RuleSet.model_validate_json(response.content)


async def load_rules(
    client: httpx.AsyncClient,
    url: str | None,
    *,
    pii_required: bool,
) -> RuleSet | None:
    """Load the active ruleset: fetched when possible, baked otherwise.

    Args:
        client: the relay's httpx client (no retries configured).
        url: the rules-API URL; ``None`` skips the fetch entirely.
        pii_required: whether any channel has PII enabled; governs fail-closed behavior.

    Raises:
        RuntimeError: no valid ruleset is available while PII is enabled.
    """
    if url is not None:
        try:
            fetched = await _fetch_rules(client, url)
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            # Log the error type only; rule contents / URLs may embed credentials.
            logger.bind(error_type=type(exc).__name__).warning("Rules fetch failed; using baked fallback")
        else:
            logger.bind(rules_version=fetched.rules_version).info("Rules loaded from API")
            return fetched
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
