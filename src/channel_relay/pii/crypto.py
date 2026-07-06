"""PII crypto keyring: epoch-indexed master keys + HKDF-derived field keys (§8.3, D4).

The keyring is ``{epoch: base64(32 bytes)}`` with epochs 0-15 (the token control byte
carries 4 epoch bits). Master keys are never used directly as cipher keys; ``K_enc`` is
derived per epoch via HKDF-SHA256 with a fixed domain-separation info string. Key material
must never appear in logs or error messages.
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
_MAX_EPOCH = 15
_HKDF_INFO_ENC = b"wenrix-pii-enc-v1"
_HKDF_INFO_SIV = b"wenrix-pii-siv-v1"


class KeyringError(ValueError):
    """The keyring source is invalid (format, epoch range, key length, active epoch)."""


class UnknownEpochError(KeyringError):
    """A token references an epoch that is not present in the keyring."""

    def __init__(self, epoch: int) -> None:
        super().__init__(f"key epoch {epoch} not present in keyring")
        self.epoch = epoch


def _derive_enc_key(master: bytes) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=_KEY_BYTES, salt=None, info=_HKDF_INFO_ENC)
    return hkdf.derive(master)


def _derive_siv_key(master: bytes) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=_SIV_KEY_BYTES, salt=None, info=_HKDF_INFO_SIV)
    return hkdf.derive(master)


class Keyring:
    """Validated epoch→(``K_enc``, ``K_siv``) keyring with an active epoch for new encryptions."""

    def __init__(self, enc_keys: dict[int, bytes], siv_keys: dict[int, bytes], active_epoch: int) -> None:
        self._enc_keys = enc_keys
        self._siv_keys = siv_keys
        self._active_epoch = active_epoch

    @classmethod
    def from_json(cls, text: str, active_epoch: int | None = None) -> Keyring:
        """Parse and validate a ``{epoch: base64(32B)}`` JSON document.

        Raises:
            KeyringError: malformed JSON, non-integer or out-of-range epoch, wrong key
                length, undecodable key, empty keyring, or missing active epoch. Messages
                never include key material.
        """
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise KeyringError(f"keyring is not valid JSON: {exc.msg}") from exc
        if not isinstance(raw, dict) or not raw:
            raise KeyringError("keyring must be a non-empty JSON object")

        enc_keys: dict[int, bytes] = {}
        siv_keys: dict[int, bytes] = {}
        for epoch_text, key_b64 in raw.items():
            try:
                epoch = int(epoch_text)
            except (TypeError, ValueError) as exc:
                raise KeyringError(f"keyring epoch {epoch_text!r} is not an integer") from exc
            if not 0 <= epoch <= _MAX_EPOCH:
                raise KeyringError(f"keyring epoch {epoch} outside 0-{_MAX_EPOCH}")
            if not isinstance(key_b64, str):
                raise KeyringError(f"keyring epoch {epoch} key must be a base64 string")
            try:
                master = pybase64.b64decode(key_b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise KeyringError(f"keyring epoch {epoch} key is not valid base64") from exc
            if len(master) != _KEY_BYTES:
                raise KeyringError(f"keyring epoch {epoch} key must decode to {_KEY_BYTES} bytes")
            enc_keys[epoch] = _derive_enc_key(master)
            siv_keys[epoch] = _derive_siv_key(master)

        if active_epoch is None:
            active_epoch = max(enc_keys)
        elif active_epoch not in enc_keys:
            raise KeyringError(f"active key epoch {active_epoch} not present in keyring")
        return cls(enc_keys, siv_keys, active_epoch)

    @property
    def epochs(self) -> tuple[int, ...]:
        """Available epoch ids (sorted); safe to expose (never key material)."""
        return tuple(sorted(self._enc_keys))

    @property
    def active_epoch(self) -> int:
        """The epoch used for new encryptions."""
        return self._active_epoch

    def enc_key(self, epoch: int) -> bytes:
        """The derived ``K_enc`` for ``epoch``.

        Raises:
            UnknownEpochError: the epoch is not in the keyring.
        """
        try:
            return self._enc_keys[epoch]
        except KeyError:
            raise UnknownEpochError(epoch) from None

    def siv_key(self, epoch: int) -> bytes:
        """The derived ``K_siv`` (64 bytes, AES-256-SIV) for ``epoch``.

        Raises:
            UnknownEpochError: the epoch is not in the keyring.
        """
        try:
            return self._siv_keys[epoch]
        except KeyError:
            raise UnknownEpochError(epoch) from None


def load_keyring(
    inline: str | None,
    file_path: str | None,
    active_epoch: int | None = None,
) -> Keyring | None:
    """Load the keyring from a mounted file (wins) or the inline setting.

    Returns ``None`` when neither source is configured (PII must then stay disabled).

    Raises:
        KeyringError: the configured file is missing or either source is invalid.
    """
    if file_path is not None:
        path = Path(file_path)
        if not path.exists():
            raise KeyringError(f"keyring file not found: {file_path}")
        return Keyring.from_json(path.read_text(encoding="utf-8"), active_epoch)
    if inline is not None:
        return Keyring.from_json(inline, active_epoch)
    return None
