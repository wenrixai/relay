"""Tests for the vendored pure-Python smaz codec (T2.2)."""

from __future__ import annotations

import pytest

from channel_relay.pii.smaz import compress, decompress


@pytest.mark.parametrize(
    "text",
    [
        b"",
        b"the",
        b"John Smith",
        b"jane.doe@example.com",
        b"the quick brown fox jumps over the lazy dog",
        b"1234567890",
        b"\x00\xff\xfe binary bytes \x01",
        "Zoë Müller-Ångström".encode(),
    ],
)
def test_round_trip(text: bytes) -> None:
    assert decompress(compress(text)) == text


def test_common_english_compresses_smaller() -> None:
    text = b"this is a test of the compression"
    assert len(compress(text)) < len(text)


def test_incompressible_bytes_do_not_explode() -> None:
    # Worst case (all verbatim) must stay bounded: escape overhead only.
    text = bytes(range(128, 200))
    assert len(compress(text)) <= len(text) + 2 + len(text) // 255 + 1


def test_pinned_vectors() -> None:
    # Self-consistency pins: any codebook change breaks outstanding tokens.
    assert compress(b"the") == bytes([1])
    assert compress(b" ") == bytes([0])
    assert decompress(bytes([1, 0, 1])) == b"the the"


def test_verbatim_single_byte() -> None:
    assert decompress(compress(b"~")) == b"~"


def test_long_verbatim_run_round_trips() -> None:
    text = bytes([200]) * 1000
    assert decompress(compress(text)) == text


def test_decompress_truncated_escape_rejected() -> None:
    with pytest.raises(ValueError):
        decompress(bytes([254]))  # escape without payload
    with pytest.raises(ValueError):
        decompress(bytes([255, 10, 1, 2]))  # length says 11, payload short
