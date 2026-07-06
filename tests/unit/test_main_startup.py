"""Startup fail-fast for auth misconfiguration (§9.2).

Basic auth must fail *closed*: an enabled-but-unconfigured relay aborts startup rather than
serving the data-plane routes open. Mirrors the keyring fail-fast in ``test_pii_crypto``.
"""

from __future__ import annotations

import pytest

from channel_relay.main import validate_auth_config
from channel_relay.settings import Settings


def test_startup_aborts_when_auth_enabled_without_credentials() -> None:
    settings = Settings(basic_auth_enabled=True, basic_auth_user=None, basic_auth_pass=None)
    with pytest.raises(RuntimeError, match="credential"):
        validate_auth_config(settings)


def test_startup_aborts_when_auth_enabled_with_only_user() -> None:
    settings = Settings(basic_auth_enabled=True, basic_auth_user="u", basic_auth_pass=None)
    with pytest.raises(RuntimeError, match="credential"):
        validate_auth_config(settings)


def test_startup_tolerates_auth_explicitly_disabled() -> None:
    settings = Settings(basic_auth_enabled=False, basic_auth_user=None, basic_auth_pass=None)
    validate_auth_config(settings)  # no raise


def test_startup_tolerates_auth_enabled_with_credentials() -> None:
    settings = Settings(basic_auth_enabled=True, basic_auth_user="u", basic_auth_pass="p")
    validate_auth_config(settings)  # no raise
