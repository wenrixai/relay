"""Property and contract tests for the ENC_ token codec (T2.2, §8.4)."""

from __future__ import annotations

import contextlib
import json
import re

import pybase64
import pytest

from channel_relay.pii.codec import TOKEN_RE, TokenError, decrypt, encrypt
from channel_relay.pii.crypto import Keyring

TOKEN_CONTRACT = re.compile(r"^ENC_[A-Za-z0-9_-]+$")

# 1 control byte + 12-byte IV; fixed pre-base64 overhead (§8.4).
FIXED_OVERHEAD = 13


def make_keyring(epochs: dict[int, int], active: int | None = None) -> Keyring:
    ring = {str(e): pybase64.b64encode(bytes([seed]) * 32).decode() for e, seed in epochs.items()}
    return Keyring.from_json(json.dumps(ring), active_epoch=active)


@pytest.fixture(name="keyring")
def keyring_fixture() -> Keyring:
    return make_keyring({0: 1, 1: 2})


@pytest.mark.parametrize(
    "plaintext",
    [
        "a",
        "John Smith",
        "jane.doe@example.com",
        "+44 20 7946 0958",
        "Zoë Müller-Ångström",
        "日本語テキスト",
        "x" * 500,
        " leading and trailing ",
    ],
)
def test_round_trip(keyring: Keyring, plaintext: str) -> None:
    assert decrypt(encrypt(plaintext, keyring), keyring) == plaintext


def test_token_matches_contract_regex(keyring: Keyring) -> None:
    for plaintext in ("short", "with spaces & symbols!", "日本語"):
        token = encrypt(plaintext, keyring)
        assert TOKEN_CONTRACT.fullmatch(token)
        assert TOKEN_RE.fullmatch(token)


def test_iv_uniqueness(keyring: Keyring) -> None:
    tokens = {encrypt("same value", keyring) for _ in range(200)}
    assert len(tokens) == 200


def test_size_bound(keyring: Keyring) -> None:
    for plaintext in ("a", "ab", "John Smith", "日本語テキスト", "y" * 300):
        raw_len = len(plaintext.encode())
        token = encrypt(plaintext, keyring)
        payload = pybase64.urlsafe_b64decode(token[len("ENC_") :] + "==")
        assert len(payload) <= raw_len + FIXED_OVERHEAD


def test_compressible_uses_smaz_flag(keyring: Keyring) -> None:
    token = encrypt("this is a test of the compression", keyring)
    payload = pybase64.urlsafe_b64decode(token[len("ENC_") :] + "==")
    assert payload[0] & 0x10  # compressed flag set


def test_incompressible_stays_raw(keyring: Keyring) -> None:
    token = encrypt("日本語", keyring)
    payload = pybase64.urlsafe_b64decode(token[len("ENC_") :] + "==")
    assert not payload[0] & 0x10


def test_active_epoch_encoded_in_control(keyring: Keyring) -> None:
    token = encrypt("value", keyring)
    payload = pybase64.urlsafe_b64decode(token[len("ENC_") :] + "==")
    assert payload[0] & 0x0F == keyring.active_epoch


def test_old_epoch_still_decrypts() -> None:
    old = make_keyring({0: 1}, active=0)
    token = encrypt("historic", old)
    rotated = make_keyring({0: 1, 1: 9}, active=1)
    assert decrypt(token, rotated) == "historic"


def test_unknown_epoch_fails(keyring: Keyring) -> None:
    token = encrypt("value", make_keyring({5: 7}))
    with pytest.raises(TokenError) as excinfo:
        decrypt(token, make_keyring({0: 1}))
    assert "5" in str(excinfo.value)


def test_wrong_key_garbles_or_fails(keyring: Keyring) -> None:
    token = encrypt("John Smith", make_keyring({0: 1}))
    other = make_keyring({0: 99})
    # A smaz/utf-8 decode failure (TokenError) is equally acceptable to garbled output.
    with contextlib.suppress(TokenError):
        assert decrypt(token, other) != "John Smith"


def test_malformed_base64_fails(keyring: Keyring) -> None:
    with pytest.raises(TokenError):
        decrypt("ENC_%%%not-base64%%%", keyring)


def test_truncated_payload_fails(keyring: Keyring) -> None:
    short = "ENC_" + pybase64.urlsafe_b64encode(b"\x00" + b"\x01" * 5).decode().rstrip("=")
    with pytest.raises(TokenError):
        decrypt(short, keyring)


def test_reserved_control_bits_rejected(keyring: Keyring) -> None:
    token = encrypt("value", keyring)
    payload = bytearray(pybase64.urlsafe_b64decode(token[len("ENC_") :] + "=="))
    payload[0] |= 0x80  # set a reserved bit
    forged = "ENC_" + pybase64.urlsafe_b64encode(bytes(payload)).decode().rstrip("=")
    with pytest.raises(TokenError):
        decrypt(forged, keyring)


def test_missing_prefix_rejected(keyring: Keyring) -> None:
    token = encrypt("value", keyring)
    with pytest.raises(TokenError):
        decrypt(token.removeprefix("ENC_"), keyring)


# --- Deterministic (AES-SIV) mode ---


def _control(token: str) -> int:
    return pybase64.urlsafe_b64decode(token[len("ENC_") :] + "==")[0]


def test_deterministic_tokens_are_identical(keyring: Keyring) -> None:
    tokens = {encrypt("John Smith", keyring, deterministic=True) for _ in range(50)}
    assert len(tokens) == 1


@pytest.mark.parametrize(
    "plaintext",
    ["a", "John Smith", "Zoë Müller-Ångström", "日本語テキスト", "x" * 500, " padded "],
)
def test_deterministic_round_trip(keyring: Keyring, plaintext: str) -> None:
    token = encrypt(plaintext, keyring, deterministic=True)
    assert decrypt(token, keyring) == plaintext


def test_deterministic_token_matches_contract(keyring: Keyring) -> None:
    token = encrypt("value", keyring, deterministic=True)
    assert TOKEN_RE.fullmatch(token)


def test_deterministic_flag_encoded_in_control(keyring: Keyring) -> None:
    assert _control(encrypt("value", keyring, deterministic=True)) & 0x20
    assert not _control(encrypt("value", keyring)) & 0x20


def test_deterministic_distinct_plaintexts_differ(keyring: Keyring) -> None:
    assert encrypt("John", keyring, deterministic=True) != encrypt("Jane", keyring, deterministic=True)


def test_deterministic_epoch_rotation_changes_token() -> None:
    old = make_keyring({0: 1}, active=0)
    token_old = encrypt("John Smith", old, deterministic=True)
    rotated = make_keyring({0: 1, 1: 9}, active=1)
    token_new = encrypt("John Smith", rotated, deterministic=True)
    assert token_old != token_new
    assert decrypt(token_old, rotated) == "John Smith"
    assert decrypt(token_new, rotated) == "John Smith"


def test_deterministic_tampered_ciphertext_fails(keyring: Keyring) -> None:
    token = encrypt("John Smith", keyring, deterministic=True)
    payload = bytearray(pybase64.urlsafe_b64decode(token[len("ENC_") :] + "=="))
    payload[-1] ^= 0x01
    forged = "ENC_" + pybase64.urlsafe_b64encode(bytes(payload)).decode().rstrip("=")
    with pytest.raises(TokenError):
        decrypt(forged, keyring)


def test_deterministic_truncated_payload_fails(keyring: Keyring) -> None:
    # control byte + fewer bytes than the 16-byte SIV tag
    short = "ENC_" + pybase64.urlsafe_b64encode(bytes([0x20]) + b"\x01" * 10).decode().rstrip("=")
    with pytest.raises(TokenError):
        decrypt(short, keyring)


def test_deterministic_compressible_round_trip(keyring: Keyring) -> None:
    plaintext = "this is a test of the compression"
    token = encrypt(plaintext, keyring, deterministic=True)
    assert _control(token) & 0x10
    assert decrypt(token, keyring) == plaintext


def test_deterministic_incompressible_round_trip(keyring: Keyring) -> None:
    token = encrypt("日本語", keyring, deterministic=True)
    assert not _control(token) & 0x10
    assert decrypt(token, keyring) == "日本語"


def test_deterministic_unknown_epoch_fails(keyring: Keyring) -> None:
    token = encrypt("value", make_keyring({5: 7}), deterministic=True)
    with pytest.raises(TokenError) as excinfo:
        decrypt(token, make_keyring({0: 1}))
    assert "5" in str(excinfo.value)


def test_remaining_reserved_bits_still_rejected(keyring: Keyring) -> None:
    for bit in (0x40, 0x80):
        token = encrypt("value", keyring, deterministic=True)
        payload = bytearray(pybase64.urlsafe_b64decode(token[len("ENC_") :] + "=="))
        payload[0] |= bit
        forged = "ENC_" + pybase64.urlsafe_b64encode(bytes(payload)).decode().rstrip("=")
        with pytest.raises(TokenError):
            decrypt(forged, keyring)
