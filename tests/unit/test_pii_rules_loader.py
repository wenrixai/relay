"""Rules loader tests: local-only load from the baked bundle, fail-closed policy (T2.4, §8.8)."""

from __future__ import annotations

import json

import pytest

from channel_relay.pii import rules as rules_module
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.rules_loader import load_baked_rules, load_rules


async def test_baked_bundle_loads_directly() -> None:
    loaded = await load_rules(pii_required=True)
    assert loaded is not None
    assert loaded.rules_version == load_baked_rules().rules_version


def test_baked_bundle_is_valid() -> None:
    baked = load_baked_rules()
    assert isinstance(baked, RuleSet)


async def test_invalid_baked_aborts_when_pii_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("channel_relay.pii.rules_loader._read_baked_text", lambda: json.dumps({"nope": 1}))

    with pytest.raises(RuntimeError, match="baked"):
        await load_rules(pii_required=True)


async def test_invalid_baked_tolerated_without_pii(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("channel_relay.pii.rules_loader._read_baked_text", lambda: json.dumps({"nope": 1}))
    loaded = await load_rules(pii_required=False)
    assert loaded is None


def test_module_split_marker() -> None:
    # Loader lives beside the models; both under channel_relay.pii.
    assert rules_module.__name__ == "channel_relay.pii.rules"
