"""PII crypto keyring: a single master key + HKDF-derived field keys (§8.3).

The keyring source is a base64(32-byte) master key (a legacy single-entry
``{"<int>": base64(32B)}`` object is also accepted for already-provisioned secrets). The
master key is never used directly as a cipher key; ``K_enc`` and ``K_siv`` are derived via
HKDF-SHA256 with fixed, distinct domain-separation info strings. Key material must never
appear in logs or error messages. Key rotation is intentionally not handled here — it will
be reintroduced later through a dedicated KMS store plugin.
"""

from __future__ import annotations

import binascii
import json
from pathlib import Path

import pybase64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_KEY_BYTES = 32
_SIV_KEY_BYTES = 64  # AES-256-SIV takes a double-length key (RFC 5297)
_HKDF_INFO_ENC = b"wenrix-pii-enc-v1"
_HKDF_INFO_SIV = b"wenrix-pii-siv-v1"


class KeyringError(ValueError):
    """The keyring source is invalid (format, key length, or unsupported multi-key)."""


def _derive_enc_key(master: bytes) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=_KEY_BYTES, salt=None, info=_HKDF_INFO_ENC)
    return hkdf.derive(master)


def _derive_siv_key(master: bytes) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=_SIV_KEY_BYTES, salt=None, info=_HKDF_INFO_SIV)
    return hkdf.derive(master)


def _decode_master(key_b64: object) -> bytes:
    """Decode and length-check a base64 master key. Never echoes key material."""
    if not isinstance(key_b64, str):
        raise KeyringError("keyring key must be a base64 string")
    try:
        master = pybase64.b64decode(key_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KeyringError("keyring key is not valid base64") from exc
    if len(master) != _KEY_BYTES:
        raise KeyringError(f"keyring key must decode to {_KEY_BYTES} bytes")
    return master


def _master_from_legacy_object(text: str) -> bytes:
    """Extract the sole master key from a legacy ``{"0": base64}`` object.

    Only the single-key ``{"0": ...}`` shape is accepted (the format every relay Secret was
    ever provisioned with). A multi-entry object is rejected because key rotation was removed.
    A single entry under a **non-zero** key is also rejected: its outstanding tokens carry that
    epoch in the control byte and would now fail closed on the widened reserved-bit mask, so a
    silent load would 502 every one of them — abort loudly instead.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise KeyringError(f"keyring is not valid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict) or not raw:
        raise KeyringError("keyring must be a non-empty JSON object or a base64 key")
    if len(raw) > 1:
        raise KeyringError("keyring has multiple keys; key rotation was removed (provide one key)")
    ((key_name, key_b64),) = raw.items()
    if str(key_name) != "0":
        raise KeyringError('keyring key rotation was removed; the legacy object must be a single {"0": key}')
    return _decode_master(key_b64)


class Keyring:
    """Validated single-master keyring exposing derived ``K_enc`` and ``K_siv``."""

    def __init__(self, enc_key: bytes, siv_key: bytes) -> None:
        self._enc_key = enc_key
        self._siv_key = siv_key

    @classmethod
    def from_json(cls, text: str) -> Keyring:
        """Parse and validate a keyring source (bare base64 key or single-entry object).

        Raises:
            KeyringError: malformed JSON, wrong key length, undecodable key, empty source,
                or a multi-key (rotation) object. Messages never include key material.
        """
        stripped = text.strip()
        if stripped.startswith("{"):
            master = _master_from_legacy_object(stripped)
        else:
            master = _decode_master(stripped)
        return cls(_derive_enc_key(master), _derive_siv_key(master))

    @property
    def enc_key(self) -> bytes:
        """The derived 32-byte ``K_enc`` field-encryption key."""
        return self._enc_key

    @property
    def siv_key(self) -> bytes:
        """The derived 64-byte ``K_siv`` deterministic-encryption key (AES-256-SIV)."""
        return self._siv_key


def load_keyring(inline: str | None, file_path: str | None) -> Keyring | None:
    """Load the keyring from a mounted file (wins) or the inline setting.

    Returns ``None`` when neither source is configured (PII must then stay disabled).

    Raises:
        KeyringError: the configured file is missing or either source is invalid.
    """
    if file_path is not None:
        path = Path(file_path)
        if not path.exists():
            raise KeyringError(f"keyring file not found: {file_path}")
        return Keyring.from_json(path.read_text(encoding="utf-8"))
    if inline is not None:
        return Keyring.from_json(inline)
    return None
