"""Tests for the PII crypto keyring: loading, epochs, HKDF derivation (T2.1)."""

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
    UnknownEpochError,
    load_keyring,
)
from channel_relay.settings import Settings


def b64key(seed: int) -> str:
    """A deterministic base64 32-byte key for tests."""
    return pybase64.b64encode(bytes([seed]) * 32).decode()


def keyring_json(epochs: dict[int, str]) -> str:
    return json.dumps({str(epoch): key for epoch, key in epochs.items()})


def test_valid_keyring_loads_epochs() -> None:
    keyring = Keyring.from_json(keyring_json({0: b64key(1), 1: b64key(2)}))
    assert keyring.epochs == (0, 1)
    assert len(keyring.enc_key(0)) == 32
    assert len(keyring.enc_key(1)) == 32


def test_epoch_out_of_range_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json(keyring_json({16: b64key(1)}))
    with pytest.raises(KeyringError):
        Keyring.from_json(keyring_json({-1: b64key(1)}))


def test_non_integer_epoch_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json(json.dumps({"zero": b64key(1)}))


def test_wrong_key_length_rejected() -> None:
    short = pybase64.b64encode(b"short").decode()
    with pytest.raises(KeyringError):
        Keyring.from_json(keyring_json({0: short}))


def test_malformed_base64_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json(json.dumps({"0": "!!!not-base64!!!"}))


def test_malformed_json_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json("{not json")


def test_empty_keyring_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json("{}")


def test_active_epoch_defaults_to_highest() -> None:
    keyring = Keyring.from_json(keyring_json({0: b64key(1), 3: b64key(2)}))
    assert keyring.active_epoch == 3


def test_configured_active_epoch_used() -> None:
    keyring = Keyring.from_json(keyring_json({0: b64key(1), 3: b64key(2)}), active_epoch=0)
    assert keyring.active_epoch == 0


def test_configured_active_epoch_missing_rejected() -> None:
    with pytest.raises(KeyringError):
        Keyring.from_json(keyring_json({0: b64key(1)}), active_epoch=5)


def test_hkdf_derivation_deterministic() -> None:
    ring_a = Keyring.from_json(keyring_json({0: b64key(1)}))
    ring_b = Keyring.from_json(keyring_json({0: b64key(1)}))
    assert ring_a.enc_key(0) == ring_b.enc_key(0)


def test_different_epoch_keys_derive_differently() -> None:
    keyring = Keyring.from_json(keyring_json({0: b64key(1), 1: b64key(2)}))
    assert keyring.enc_key(0) != keyring.enc_key(1)


def test_derived_key_differs_from_master() -> None:
    keyring = Keyring.from_json(keyring_json({0: b64key(1)}))
    assert keyring.enc_key(0) != bytes([1]) * 32


def test_unknown_epoch_raises_with_epoch_only() -> None:
    keyring = Keyring.from_json(keyring_json({0: b64key(7)}))
    with pytest.raises(UnknownEpochError) as excinfo:
        keyring.enc_key(9)
    message = str(excinfo.value)
    assert "9" in message
    assert b64key(7) not in message


def test_error_messages_never_contain_key_material() -> None:
    with pytest.raises(KeyringError) as excinfo:
        Keyring.from_json(keyring_json({16: b64key(5)}))
    assert b64key(5) not in str(excinfo.value)


def test_load_keyring_returns_none_without_sources() -> None:
    assert load_keyring(inline=None, file_path=None) is None


def test_load_keyring_from_inline() -> None:
    keyring = load_keyring(inline=keyring_json({0: b64key(1)}), file_path=None)
    assert keyring is not None
    assert keyring.epochs == (0,)


def test_load_keyring_file_wins_over_inline(tmp_path: Path) -> None:
    path = tmp_path / "keyring.json"
    path.write_text(keyring_json({2: b64key(9)}))
    keyring = load_keyring(inline=keyring_json({0: b64key(1)}), file_path=str(path))
    assert keyring is not None
    assert keyring.epochs == (2,)


def test_load_keyring_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(KeyringError):
        load_keyring(inline=None, file_path=str(tmp_path / "absent.json"))


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
    settings = Settings(pii_keyring=keyring_json({0: b64key(1)}))
    keyring = build_keyring(settings, _config_with_pii(enabled=True))
    assert keyring is not None
    assert keyring.active_epoch == 0


def test_startup_rejects_invalid_keyring_even_without_pii() -> None:
    settings = Settings(pii_keyring="{not json")
    with pytest.raises(KeyringError):
        build_keyring(settings, _config_with_pii(enabled=False))
