"""Rules loader tests: startup fetch, baked fallback, fail-closed policy (T2.4, §8.8)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from channel_relay.pii import rules as rules_module
from channel_relay.pii.rules import RuleSet
from channel_relay.pii.rules_loader import load_baked_rules, load_rules

VALID_DOC: dict[str, Any] = {
    "schema_version": "1.0",
    "rules_version": "2026-07-02",
    "rules": [
        {
            "id": "mock.op.person.001",
            "channel": "mock",
            "operation": ".*",
            "path": "//Name",
            "pii_type": "person",
            "method": "encrypt",
        }
    ],
}


def client_returning(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_successful_fetch_wins() -> None:
    client = client_returning(lambda request: httpx.Response(200, json=VALID_DOC))
    loaded = await load_rules(client, "https://rules.wenrix.test/v1", pii_required=True)
    assert loaded is not None
    assert loaded.rules_version == "2026-07-02"


async def test_single_attempt_no_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("boom")

    loaded = await load_rules(client_returning(handler), "https://r.test", pii_required=False)
    assert calls == 1
    assert loaded is not None  # baked fallback
    assert loaded.rules_version == load_baked_rules().rules_version


async def test_timeout_falls_back_to_baked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    loaded = await load_rules(client_returning(handler), "https://r.test", pii_required=True)
    assert loaded is not None
    assert loaded.rules_version == load_baked_rules().rules_version


async def test_http_error_falls_back() -> None:
    client = client_returning(lambda request: httpx.Response(500, text="oops"))
    loaded = await load_rules(client, "https://r.test", pii_required=True)
    assert loaded is not None
    assert loaded.rules_version == load_baked_rules().rules_version


async def test_malformed_json_falls_back() -> None:
    client = client_returning(lambda request: httpx.Response(200, text="{not json"))
    loaded = await load_rules(client, "https://r.test", pii_required=True)
    assert loaded is not None
    assert loaded.rules_version == load_baked_rules().rules_version


async def test_incompatible_schema_falls_back() -> None:
    doc = dict(VALID_DOC, schema_version="9.0")
    client = client_returning(lambda request: httpx.Response(200, json=doc))
    loaded = await load_rules(client, "https://r.test", pii_required=True)
    assert loaded is not None
    assert loaded.rules_version == load_baked_rules().rules_version


async def test_no_url_uses_baked_directly() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=VALID_DOC)

    loaded = await load_rules(client_returning(handler), None, pii_required=False)
    assert calls == 0
    assert loaded is not None


def test_baked_bundle_is_valid() -> None:
    baked = load_baked_rules()
    assert isinstance(baked, RuleSet)


async def test_invalid_baked_aborts_when_pii_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("channel_relay.pii.rules_loader._read_baked_text", lambda: json.dumps({"nope": 1}))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(RuntimeError, match="baked"):
        await load_rules(client_returning(handler), "https://r.test", pii_required=True)


async def test_invalid_baked_tolerated_without_pii(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("channel_relay.pii.rules_loader._read_baked_text", lambda: json.dumps({"nope": 1}))
    loaded = await load_rules(client_returning(lambda r: httpx.Response(500)), None, pii_required=False)
    assert loaded is None


def test_module_split_marker() -> None:
    # Loader lives beside the models; both under channel_relay.pii.
    assert rules_module.__name__ == "channel_relay.pii.rules"
