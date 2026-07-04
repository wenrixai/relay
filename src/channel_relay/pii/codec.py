"""ENC_ token codec: AES-256-CTR field encryption with smaz pre-compression (§8.4, D1-D3).

Token layout: ``ENC_ + base64url_nopad(control ‖ iv ‖ ciphertext)`` where ``control`` is
one byte (bits 0-3 key epoch, bit 4 compressed flag, bits 5-7 reserved zero — the version
headroom) and ``iv`` is 12 random bytes. Confidentiality-only in v1: TLS provides
transport integrity per the threat model. The IV must never drop below 96 bits.
"""

from __future__ import annotations

import binascii
import os
import re

import pybase64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from channel_relay.pii import smaz
from channel_relay.pii.crypto import Keyring, UnknownEpochError

TOKEN_PREFIX = "ENC_"
TOKEN_RE = re.compile(r"^ENC_[A-Za-z0-9_-]+$")

_IV_BYTES = 12  # 96-bit; never reduce (§8.4)
_CTR_SUFFIX = b"\x00\x00\x00\x00"
_EPOCH_MASK = 0x0F
_COMPRESSED_FLAG = 0x10
_RESERVED_MASK = 0xE0


class TokenError(ValueError):
    """A token failed decoding/decryption. Messages never include plaintext or keys."""


def _ctr(key: bytes, iv: bytes) -> Cipher[modes.CTR]:
    return Cipher(algorithms.AES(key), modes.CTR(iv + _CTR_SUFFIX))


def encrypt(plaintext: str, keyring: Keyring) -> str:
    """Encrypt ``plaintext`` into an ``ENC_`` token under the keyring's active epoch."""
    raw = plaintext.encode()
    compressed = smaz.compress(raw)
    if len(compressed) < len(raw):
        payload, control = compressed, _COMPRESSED_FLAG
    else:
        payload, control = raw, 0
    epoch = keyring.active_epoch
    control |= epoch & _EPOCH_MASK
    iv = os.urandom(_IV_BYTES)
    encryptor = _ctr(keyring.enc_key(epoch), iv).encryptor()
    ciphertext = encryptor.update(payload) + encryptor.finalize()
    packed = bytes([control]) + iv + ciphertext
    return TOKEN_PREFIX + pybase64.urlsafe_b64encode(packed).decode().rstrip("=")


def decrypt(token: str, keyring: Keyring) -> str:
    """Decrypt an ``ENC_`` token back to plaintext.

    Raises:
        TokenError: missing prefix, malformed base64, truncated payload, reserved control
            bits set, unknown epoch, or a payload that fails decompression/UTF-8 decode.
    """
    if not token.startswith(TOKEN_PREFIX):
        raise TokenError("token missing ENC_ prefix")
    body = token[len(TOKEN_PREFIX) :]
    try:
        packed = pybase64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TokenError("token is not valid base64url") from exc
    if len(packed) < 1 + _IV_BYTES:
        raise TokenError("token payload truncated")
    control, iv, ciphertext = packed[0], packed[1 : 1 + _IV_BYTES], packed[1 + _IV_BYTES :]
    if control & _RESERVED_MASK:
        raise TokenError("token reserved control bits set (unsupported version)")
    epoch = control & _EPOCH_MASK
    try:
        key = keyring.enc_key(epoch)
    except UnknownEpochError as exc:
        raise TokenError(str(exc)) from exc
    decryptor = _ctr(key, iv).decryptor()
    payload = decryptor.update(ciphertext) + decryptor.finalize()
    if control & _COMPRESSED_FLAG:
        try:
            payload = smaz.decompress(payload)
        except ValueError as exc:
            raise TokenError("token decompression failed") from exc
    try:
        return payload.decode()
    except UnicodeDecodeError as exc:
        raise TokenError("token plaintext is not valid UTF-8") from exc
