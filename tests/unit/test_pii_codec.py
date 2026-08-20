"""Property and contract tests for the ENC_ token codec (T2.2, §8.4)."""

from __future__ import annotations

import contextlib
import re

import pybase64
import pytest

from channel_relay.pii.codec import TOKEN_RE, TokenError, decrypt, encrypt
from channel_relay.pii.crypto import Keyring

TOKEN_CONTRACT = re.compile(r"^ENC_[A-Za-z0-9_-]+$")

# 1 control byte + 12-byte IV; fixed pre-base64 overhead of the random-IV mode (§8.4).
FIXED_OVERHEAD = 13
# 1 control byte + 16-byte SIV tag; fixed pre-base64 overhead of the default mode (§8.4).
SIV_FIXED_OVERHEAD = 17


def make_keyring(seed: int = 1) -> Keyring:
    return Keyring.from_json(pybase64.b64encode(bytes([seed]) * 32).decode())


@pytest.fixture(name="keyring")
def keyring_fixture() -> Keyring:
    return make_keyring()


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
    tokens = {encrypt("same value", keyring, deterministic=False) for _ in range(200)}
    assert len(tokens) == 200


def test_size_bound(keyring: Keyring) -> None:
    for plaintext in ("a", "ab", "John Smith", "日本語テキスト", "y" * 300):
        raw_len = len(plaintext.encode())
        token = encrypt(plaintext, keyring, deterministic=False)
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


def test_former_epoch_bits_written_zero(keyring: Keyring) -> None:
    token = encrypt("value", keyring)
    payload = pybase64.urlsafe_b64decode(token[len("ENC_") :] + "==")
    assert payload[0] & 0x0F == 0  # bits 0-3 (former key epoch) are reserved zero


def test_historic_epoch0_token_decrypts_under_single_key() -> None:
    """A token minted before rotation removal (control low nibble = 0) still round-trips.

    Locks the backward-compat guarantee: this deterministic token was produced by the codec
    when the keyring was epoch-indexed and the active epoch was 0. It must keep decrypting
    under the collapsed single-key keyring.
    """
    key = pybase64.b64encode(bytes([7]) * 32).decode()
    # Ciphertext under the fixed test key above, not a real secret.
    historic_token = "ENC_MPro6LDsEKAT725CZuK7J16XpfcInCxUAEiQLBnB"  # gitleaks:allow
    assert pybase64.urlsafe_b64decode(historic_token[len("ENC_") :] + "==")[0] & 0x0F == 0
    assert decrypt(historic_token, Keyring.from_json(key)) == "Historic Passenger"


def test_legacy_object_and_bare_key_decrypt_interchangeably() -> None:
    """A token encrypted under a legacy {"0": key} keyring decrypts under the bare-key form."""
    key = pybase64.b64encode(bytes([3]) * 32).decode()
    legacy = Keyring.from_json(f'{{"0": "{key}"}}')
    bare = Keyring.from_json(key)
    token = encrypt("Round Trip", legacy)
    assert decrypt(token, bare) == "Round Trip"


def test_wrong_key_garbles_or_fails() -> None:
    token = encrypt("John Smith", make_keyring(1))
    other = make_keyring(99)
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


def test_former_epoch_bits_rejected_on_decode(keyring: Keyring) -> None:
    for bit in (0x01, 0x02, 0x04, 0x08):  # bits 0-3 are now reserved-must-be-zero
        token = encrypt("value", keyring)
        payload = bytearray(pybase64.urlsafe_b64decode(token[len("ENC_") :] + "=="))
        payload[0] |= bit
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
    assert not _control(encrypt("value", keyring, deterministic=False)) & 0x20


def test_deterministic_distinct_plaintexts_differ(keyring: Keyring) -> None:
    assert encrypt("John", keyring, deterministic=True) != encrypt("Jane", keyring, deterministic=True)


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


def test_remaining_reserved_bits_still_rejected(keyring: Keyring) -> None:
    for bit in (0x40, 0x80):
        token = encrypt("value", keyring, deterministic=True)
        payload = bytearray(pybase64.urlsafe_b64decode(token[len("ENC_") :] + "=="))
        payload[0] |= bit
        forged = "ENC_" + pybase64.urlsafe_b64encode(bytes(payload)).decode().rstrip("=")
        with pytest.raises(TokenError):
            decrypt(forged, keyring)


def test_default_mode_is_deterministic(keyring: Keyring) -> None:
    """No mode argument means AES-SIV: bit 5 set and repeated calls byte-identical."""
    tokens = {encrypt("same value", keyring) for _ in range(50)}
    assert len(tokens) == 1
    assert _control(tokens.pop()) & 0x20


def test_default_mode_stable_across_keyring_reloads() -> None:
    """The same master key reloaded (pod restart) mints the identical default-mode token."""
    first, second = make_keyring(5), make_keyring(5)
    assert encrypt("SMITH/JOHN MR", first) == encrypt("SMITH/JOHN MR", second)


def test_default_mode_size_bound(keyring: Keyring) -> None:
    for plaintext in ("a", "ab", "John Smith", "\u65e5\u672c\u8a9e\u30c6\u30ad\u30b9\u30c8", "y" * 300):
        raw_len = len(plaintext.encode())
        payload = pybase64.urlsafe_b64decode(encrypt(plaintext, keyring)[len("ENC_") :] + "==")
        assert len(payload) <= raw_len + SIV_FIXED_OVERHEAD
