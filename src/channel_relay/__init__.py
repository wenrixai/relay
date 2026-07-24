"""Wenrix Channel Relay v2.

A privacy-first, transparent FastAPI relay for travel channels. See ``openspec/specs/``
for the canonical specification set.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as _installed_version


def _resolve_version() -> str:
    """Resolve the relay's version for OTel ``service.version`` (§13.1).

    Release images bake the git-tag version into ``RELAY_VERSION`` at build time; that
    value is authoritative and wins whenever it's set. The installed package metadata and
    the ``0.0.0+unknown`` sentinel are dev/misbuild fallbacks only — they never appear on
    a properly built release image.
    """
    env_version = os.environ.get("RELAY_VERSION")
    if env_version:
        return env_version
    try:
        return _installed_version("channel-relay")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _resolve_version()
