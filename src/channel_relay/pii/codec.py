"""ENC_ token codec: AES-256-CTR field encryption with smaz pre-compression (§8.4, D1-D3).

Token layout: ``ENC_ + base64url_nopad(control ‖ body)`` where ``control`` is one byte
(bit 4 compressed flag, bit 5 deterministic flag, bits 0-3 and 6-7 reserved zero — the
version headroom). Default mode: ``body = iv ‖ ciphertext`` with 12 random IV bytes and
AES-256-CTR under ``K_enc`` — confidentiality-only in v1 (TLS provides transport integrity
per the threat model); the IV must never drop below 96 bits. Deterministic mode (bit 5):
``body`` is AES-256-SIV (RFC 5297, no nonce) under ``K_siv`` — the same plaintext always
yields the same token, so callers can compare redacted values by equality. That equality is
a deliberate, bounded leak (opt-in per rule); the SIV tag also authenticates the token.
Deploy order matters: relays that predate bit 5 reject deterministic tokens fail-closed as
reserved-bit errors.
"""

from __future__ import annotations

import binascii
import os
import re

import pybase64
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESSIV

from channel_relay.pii import smaz
from channel_relay.pii.crypto import Keyring

TOKEN_PREFIX = "ENC_"
TOKEN_RE = re.compile(r"^ENC_[A-Za-z0-9_-]+$")

_IV_BYTES = 12  # 96-bit; never reduce (§8.4)
_SIV_TAG_BYTES = 16  # AES-SIV synthetic IV / authentication tag (RFC 5297)
_CTR_SUFFIX = b"\x00\x00\x00\x00"
_COMPRESSED_FLAG = 0x10
_DETERMINISTIC_FLAG = 0x20
_RESERVED_MASK = 0xCF  # bits 0-3 (former key epoch, now unused) and 6-7 reserved zero


class TokenError(ValueError):
    """A token failed decoding/decryption. Messages never include plaintext or keys."""


def _ctr(key: bytes, iv: bytes) -> Cipher[modes.CTR]:
    return Cipher(algorithms.AES(key), modes.CTR(iv + _CTR_SUFFIX))


def encrypt(plaintext: str, keyring: Keyring, *, deterministic: bool = False) -> str:
    """Encrypt ``plaintext`` into an ``ENC_`` token under the keyring's master key.

    ``deterministic=True`` uses AES-SIV with no nonce: the same plaintext always yields the
    identical token (an opt-in, bounded equality leak).
    """
    raw = plaintext.encode()
    compressed = smaz.compress(raw)
    if len(compressed) < len(raw):
        payload, control = compressed, _COMPRESSED_FLAG
    else:
        payload, control = raw, 0
    if deterministic:
        control |= _DETERMINISTIC_FLAG
        body = AESSIV(keyring.siv_key).encrypt(payload, None)
    else:
        iv = os.urandom(_IV_BYTES)
        encryptor = _ctr(keyring.enc_key, iv).encryptor()
        body = iv + encryptor.update(payload) + encryptor.finalize()
    packed = bytes([control]) + body
    return TOKEN_PREFIX + pybase64.urlsafe_b64encode(packed).decode().rstrip("=")


def _decrypt_siv_body(body: bytes, keyring: Keyring) -> bytes:
    """Decrypt a deterministic-mode token body (SIV tag ‖ ciphertext)."""
    if len(body) < _SIV_TAG_BYTES:
        raise TokenError("token payload truncated")
    try:
        return AESSIV(keyring.siv_key).decrypt(body, None)
    except InvalidTag as exc:
        raise TokenError("token authentication failed") from exc


def _decrypt_ctr_body(body: bytes, keyring: Keyring) -> bytes:
    """Decrypt a default-mode token body (iv ‖ ciphertext)."""
    if len(body) < _IV_BYTES:
        raise TokenError("token payload truncated")
    iv, ciphertext = body[:_IV_BYTES], body[_IV_BYTES:]
    decryptor = _ctr(keyring.enc_key, iv).decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def decrypt(token: str, keyring: Keyring) -> str:
    """Decrypt an ``ENC_`` token back to plaintext.

    Raises:
        TokenError: missing prefix, malformed base64, truncated payload, reserved control
            bits set, or a payload that fails decompression/UTF-8 decode.
    """
    if not token.startswith(TOKEN_PREFIX):
        raise TokenError("token missing ENC_ prefix")
    body = token[len(TOKEN_PREFIX) :]
    try:
        packed = pybase64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TokenError("token is not valid base64url") from exc
    if not packed:
        raise TokenError("token payload truncated")
    control = packed[0]
    if control & _RESERVED_MASK:
        raise TokenError("token reserved control bits set (unsupported version)")
    if control & _DETERMINISTIC_FLAG:
        payload = _decrypt_siv_body(packed[1:], keyring)
    else:
        payload = _decrypt_ctr_body(packed[1:], keyring)
    if control & _COMPRESSED_FLAG:
        try:
            payload = smaz.decompress(payload)
        except ValueError as exc:
            raise TokenError("token decompression failed") from exc
    try:
        return payload.decode()
    except UnicodeDecodeError as exc:
        raise TokenError("token plaintext is not valid UTF-8") from exc
