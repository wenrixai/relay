"""Tests for the PII crypto keyring: loading, single-key format, HKDF derivation (T2.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pybase64
import pytest

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import build_keyring
from channel_relay.pii.crypto import (
    Keyring,
    KeyringError,
    load_keyring,
)
from channel_relay.settings import Settings


def b64key(seed: int) -> str:
    """A deterministic base64 32-byte key for tests."""
    return pybase64.b64encode(bytes([seed]) * 32).decode()


def legacy_object(entries: dict[int, str]) -> str:
    """A legacy ``{epoch: key}`` JSON keyring document."""
    return json.dumps({str(epoch): key for epoch, key in entries.items()})


def test_bare_base64_key_loads() -> None:
    keyring = Keyring.from_json(b64key(1))
    assert len(keyring.enc_key) == 32


def test_legacy_single_entry_object_loads() -> None:
    keyring = Keyring.from_json(legacy_object({0: b64key(1)}))
    assert len(keyring.enc_key) == 32


def test_multi_entry_object_rejected() -> None:
    with pytest.raises(KeyringError, match="rotation"):
        Keyring.from_json(legacy_object({0: b64key(1), 1: b64key(2)}))


def test_single_non_zero_entry_object_rejected() -> None:
    # A one-key {"5": ...} secret loads a valid key but its epoch-5 tokens would 502; fail closed.
    with pytest.raises(KeyringError, match="rotation"):
        Keyring.from_json(legacy_object({5: b64key(1)}))


def test_wrong_key_length_rejected() -> None:
    short = pybase64.b64encode(b"short").decode()
    with pytest.raises(KeyringError):
        Keyring.from_json(short)
    with pytest.raises(KeyringError):
        Keyring.from_json(legacy_object({0: short}))


def test_malformed_base64_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json("!!!not-base64!!!")


def test_malformed_json_object_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json("{not json")


def test_empty_object_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json("{}")


def test_hkdf_derivation_deterministic() -> None:
    ring_a = Keyring.from_json(b64key(1))
    ring_b = Keyring.from_json(b64key(1))
    assert ring_a.enc_key == ring_b.enc_key


def test_derived_key_differs_from_master() -> None:
    keyring = Keyring.from_json(b64key(1))
    assert keyring.enc_key != bytes([1]) * 32


def test_siv_key_is_64_bytes() -> None:
    keyring = Keyring.from_json(b64key(1))
    assert len(keyring.siv_key) == 64


def test_siv_key_derivation_deterministic() -> None:
    ring_a = Keyring.from_json(b64key(1))
    ring_b = Keyring.from_json(b64key(1))
    assert ring_a.siv_key == ring_b.siv_key


def test_siv_key_domain_separated_from_enc_key() -> None:
    keyring = Keyring.from_json(b64key(1))
    enc, siv = keyring.enc_key, keyring.siv_key
    assert enc != siv
    assert not siv.startswith(enc)


def test_siv_key_differs_from_master() -> None:
    keyring = Keyring.from_json(b64key(1))
    assert not keyring.siv_key.startswith(bytes([1]) * 32)


def test_error_messages_never_contain_key_material() -> None:
    with pytest.raises(KeyringError) as excinfo:
        Keyring.from_json(legacy_object({0: b64key(5), 1: b64key(6)}))
    assert b64key(5) not in str(excinfo.value)
    assert b64key(6) not in str(excinfo.value)


def test_load_keyring_returns_none_without_sources() -> None:
    assert load_keyring(inline=None, file_path=None) is None


def test_load_keyring_from_inline() -> None:
    keyring = load_keyring(inline=b64key(1), file_path=None)
    assert keyring is not None
    assert len(keyring.enc_key) == 32


def test_load_keyring_file_wins_over_inline(tmp_path: Path) -> None:
    path = tmp_path / "keyring.key"
    path.write_text(b64key(9))
    keyring = load_keyring(inline=b64key(1), file_path=str(path))
    assert keyring is not None
    assert keyring.enc_key == Keyring.from_json(b64key(9)).enc_key


def test_load_keyring_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(KeyringError):
        load_keyring(inline=None, file_path=str(tmp_path / "absent.key"))


def _config_with_pii(enabled: bool) -> RelayConfig:
    return RelayConfig(
        channels=[
            ChannelConfig(
                name="mock",
                type=ChannelType.TRAVELFUSION,
                pii=ChannelPII(enabled=enabled),
            )
        ]
    )


def test_startup_aborts_when_pii_enabled_without_keyring() -> None:
    settings = Settings(pii_keyring=None, pii_keyring_file=None)
    with pytest.raises(RuntimeError, match="keyring"):
        build_keyring(settings, _config_with_pii(enabled=True))


def test_startup_tolerates_missing_keyring_when_pii_disabled() -> None:
    settings = Settings(pii_keyring=None, pii_keyring_file=None)
    assert build_keyring(settings, _config_with_pii(enabled=False)) is None


def test_startup_loads_keyring_when_configured() -> None:
    settings = Settings(pii_keyring=b64key(1))
    keyring = build_keyring(settings, _config_with_pii(enabled=True))
    assert keyring is not None
    assert len(keyring.enc_key) == 32


def test_startup_rejects_invalid_keyring_even_without_pii() -> None:
    settings = Settings(pii_keyring="{not json")
    with pytest.raises(KeyringError):
        build_keyring(settings, _config_with_pii(enabled=False))


def test_startup_tolerates_missing_keyring_when_only_force_redact_channel() -> None:
    settings = Settings(pii_keyring=None, pii_keyring_file=None)
    config = RelayConfig(
        channels=[
            ChannelConfig(
                name="mock",
                type=ChannelType.TRAVELFUSION,
                pii=ChannelPII(enabled=True, force_redact=True),
            )
        ]
    )
    assert build_keyring(settings, config) is None
