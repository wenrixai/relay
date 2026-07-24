"""Tests for the ``__version__`` resolver (RELAY_VERSION → package metadata → sentinel)."""

from __future__ import annotations

from typing import Any

from channel_relay import _resolve_version


def test_relay_version_env_wins(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_VERSION", "1.7.1")
    assert _resolve_version() == "1.7.1"


def test_missing_relay_version_falls_back_to_non_empty_string(monkeypatch: Any) -> None:
    monkeypatch.delenv("RELAY_VERSION", raising=False)
    resolved = _resolve_version()
    assert resolved != ""


def test_empty_relay_version_does_not_win(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_VERSION", "")
    resolved = _resolve_version()
    assert resolved != ""
