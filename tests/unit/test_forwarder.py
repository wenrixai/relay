"""Tests for routing + transparent pass-through forwarding (T1.6)."""

from __future__ import annotations

import gzip
from collections.abc import Callable
from typing import Any, Protocol, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response as StarletteResponse

from channel_relay.channels import get_handler
from channel_relay.config.models import ChannelConfig, ChannelType
from channel_relay.pii.codec import encrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.rules import RuleSet
from channel_relay.proxy.errors import WENRIX_ERROR_HEADER
from channel_relay.proxy.forwarder import (
    _StageContext,
    _request_credential_swap_stage,
    _request_pii_stage,
    _response_credential_swap_stage,
    _response_pii_stage,
    build_target_url,
    channel_timeout,
    find_channel,
)

KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'

RelayClientFactory = Callable[[ChannelConfig, httpx.MockTransport], TestClient]
TravelFusionClientFactory = Callable[[httpx.MockTransport], TestClient]


class ProxyErrorAssertion(Protocol):
    def __call__(self, resp: httpx.Response, status_code: int, reason: str, trace_id: str | None = None) -> None: ...


class _CountingMetrics:
    def __init__(self) -> None:
        self.xml_errors: list[tuple[str, str]] = []
        self.decrypted: list[tuple[str, int]] = []
        self.redacted: list[tuple[str, dict[str, int]]] = []
        self.uncovered: list[tuple[str, str]] = []
        self.path_errors: list[tuple[str, str]] = []

    def record_xml_parse_error(self, channel: str, kind: str) -> None:
        self.xml_errors.append((channel, kind))

    def record_pii_decrypted(self, channel: str, count: int) -> None:
        self.decrypted.append((channel, count))

    def record_pii_redacted(self, channel: str, counts: dict[str, int]) -> None:
        self.redacted.append((channel, counts))

    def record_uncovered_operation(self, channel: str, operation: str) -> None:
        self.uncovered.append((channel, operation))

    def record_pii_rule_path_error(self, channel: str, rule_id: str) -> None:
        self.path_errors.append((channel, rule_id))


def _person_ruleset(operation: str) -> RuleSet:
    return RuleSet.model_validate(
        {
            "schema_version": "1.0",
            "rules_version": "t",
            "rules": [
                {
                    "id": "person",
                    "channel": "travelfusion",
                    "operation": f"^{operation}$",
                    "path": "//Name",
                    "pii_type": "person",
                    "method": "encrypt",
                }
            ],
        }
    )


def _keyring() -> Keyring:
    return Keyring.from_json(KEYRING_JSON)


def _required_missing_ruleset() -> RuleSet:
    return RuleSet.model_validate(
        {
            "schema_version": "1.0",
            "rules_version": "t",
            "rules": [
                {
                    "id": "missing",
                    "channel": "mock",
                    "operation": "^Root$",
                    "path": "//Missing",
                    "pii_type": "person",
                    "method": "encrypt",
                    "required": True,
                }
            ],
        }
    )


def test_build_target_url_joins_base_path_query() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    url = build_target_url(channel, "CommandList", "x=1&y=2")
    assert str(url) == "https://api.travelfusion.com/CommandList?x=1&y=2"


def test_build_target_url_no_path() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    assert str(build_target_url(channel, "", "")) == "https://api.travelfusion.com"


def test_find_channel_handles_missing_config() -> None:
    assert find_channel(None, "tf") is None


def test_channel_timeout_uses_per_channel_values() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    channel.timeouts.connect = 5
    channel.timeouts.read = 7
    timeout = channel_timeout(channel)
    assert timeout.connect == 5
    assert timeout.read == 7


def test_forward_passes_method_path_query_body(travelfusion_client: TravelFusionClientFactory) -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, content=b"upstream-body", headers={"x-test": "1"})

    with travelfusion_client(httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/CommandList?x=1",
            content=b"req-body",
            headers={"content-type": "text/xml"},
        )

    assert resp.status_code == 200
    assert resp.content == b"upstream-body"
    assert resp.headers["x-test"] == "1"
    req = captured["req"]
    assert req.method == "POST"
    assert str(req.url) == "https://api.travelfusion.com/CommandList?x=1"
    assert req.content == b"req-body"


def test_forward_rewrites_host_to_channel_host(travelfusion_client: TravelFusionClientFactory) -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(204)

    with travelfusion_client(httpx.MockTransport(handler)) as client:
        client.get("/channel/tf/ping")

    assert captured["req"].headers["host"] == "api.travelfusion.com"


def test_forward_matches_bare_channel_path(travelfusion_client: TravelFusionClientFactory) -> None:
    """Old nginx proxy allowed a bare ``/channel/<name>`` with no trailing path (§ backward compat)."""
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(204)

    with travelfusion_client(httpx.MockTransport(handler)) as client:
        resp = client.get("/channel/tf")

    assert resp.status_code == 204
    assert str(captured["req"].url) == "https://api.travelfusion.com"


def test_unknown_channel_returns_404(
    travelfusion_client: TravelFusionClientFactory, unreachable_transport: httpx.MockTransport
) -> None:
    with travelfusion_client(unreachable_transport) as client:
        resp = client.get("/channel/nope/x")

    assert resp.status_code == 404


def test_channel_without_upstream_returns_internal_error(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    channel = ChannelConfig(name="gds", type=ChannelType.TRAVELPORT)

    with relay_client_factory(channel, unreachable_transport) as client:
        resp = client.get("/channel/gds/op", headers={"x-wenrix-trace-id": "trace-1"})

    assert_proxy_error(resp, 502, "internal_error", "trace-1")


def test_header_credential_swap_failure_returns_bad_gateway(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    channel = ChannelConfig(
        name="ba",
        type=ChannelType.BA_NDC_DIRECT,
        credentials={"enabled": True, "api_key_header": "X-Client-Key"},
    )

    with relay_client_factory(channel, unreachable_transport) as client:
        resp = client.get("/channel/ba/op")

    assert_proxy_error(resp, 502, "credential_swap_failed")


def test_bad_gzip_request_body_returns_xml_parse_error(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "login", "xml_login_id": "xml"},
    )

    with relay_client_factory(channel, unreachable_transport) as client:
        resp = client.post(
            "/channel/tf/op",
            content=b"not gzip",
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    assert_proxy_error(resp, 502, "xml_parse_error")


def test_gzipped_request_with_no_pii_tokens_forwarded_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    relay_client_factory: RelayClientFactory,
) -> None:
    """A PII-enabled channel must not re-gzip a request body that had zero ``ENC_`` tokens."""
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, pii={"enabled": True})
    original_xml = b"<Search><Name>Jane</Name></Search>"
    gzipped_body = gzip.compress(original_xml)
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, content=b"<Ok/>", headers={"content-type": "application/xml"})

    with relay_client_factory(channel, httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/op",
            content=gzipped_body,
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    assert resp.status_code == 200
    assert captured["req"].content == gzipped_body
    assert captured["req"].headers["content-encoding"] == "gzip"


def test_malformed_request_xml_during_credential_swap_returns_xml_parse_error(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "login", "xml_login_id": "xml"},
    )

    with relay_client_factory(channel, unreachable_transport) as client:
        resp = client.post("/channel/tf/op", content=b"<broken", headers={"content-type": "application/xml"})

    assert_proxy_error(resp, 502, "xml_parse_error")


def test_non_xml_request_requiring_structural_swap_fails_closed(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "login", "xml_login_id": "xml"},
    )

    with relay_client_factory(channel, unreachable_transport) as client:
        resp = client.post(
            "/channel/tf/op",
            content=b'{"LoginId":"caller"}',
            headers={"content-type": "application/json", "x-wenrix-trace-id": "trace-json"},
        )

    assert_proxy_error(resp, 415, "unsupported_content_type", "trace-json")


def test_non_xml_response_requiring_pii_redaction_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    relay_client_factory: RelayClientFactory,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        pii={"enabled": True},
    )
    upstream_body = b'{"passenger":"SECRET NAME"}'
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=upstream_body, headers={"content-type": "application/json"})
    )

    with relay_client_factory(channel, transport) as client:
        resp = client.post(
            "/channel/tf/op",
            content=b"<Ping/>",
            headers={"content-type": "application/xml", "x-wenrix-trace-id": "trace-upstream-json"},
        )

    assert_proxy_error(resp, 502, "unsupported_content_type", "trace-upstream-json")
    assert upstream_body not in resp.content


def test_response_credential_cleanup_parse_failure_returns_xml_parse_error(
    monkeypatch: pytest.MonkeyPatch,
    relay_client_factory: RelayClientFactory,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    channel = ChannelConfig(
        name="amadeus",
        type=ChannelType.AMADEUS,
        host="gds.test",
        credentials={"enabled": True, "soap_security": "<Security/>"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<broken", headers={"content-type": "application/xml"})

    with relay_client_factory(channel, httpx.MockTransport(handler)) as client:
        resp = client.get("/channel/amadeus/op")

    assert_proxy_error(resp, 502, "xml_parse_error")


def test_response_credential_cleanup_failure_returns_bad_gateway() -> None:
    channel = ChannelConfig(
        name="amadeus",
        type=ChannelType.AMADEUS,
        host="gds.test",
        credentials={"enabled": True, "soap_security": "<Security/>"},
    )

    resp = _response_credential_swap_stage(
        content=b"<Envelope><SessionId>SESSION-123</SessionId></Envelope>",
        response_headers={},
        keyring=None,
        ctx=_StageContext(channel=channel, max_inspect_bytes=1024, trace_id="trace-1", metrics=None),
    )

    assert isinstance(resp, StarletteResponse)
    assert resp.status_code == 502
    assert resp.headers[WENRIX_ERROR_HEADER] == "credential_swap_failed"


def test_request_credential_swap_oversize_records_metric() -> None:
    metrics = _CountingMetrics()
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "login", "xml_login_id": "xml"},
    )

    resp = _request_credential_swap_stage(
        handler=get_handler(channel.type),
        body=b"<Root/>",
        headers={},
        keyring=None,
        ctx=_StageContext(channel=channel, max_inspect_bytes=1, trace_id=None, metrics=cast(Any, metrics)),
    )

    assert isinstance(resp, StarletteResponse)
    assert resp.status_code == 413
    assert metrics.xml_errors == [("tf", "oversize")]


def test_response_credential_cleanup_oversize_records_metric() -> None:
    metrics = _CountingMetrics()
    channel = ChannelConfig(
        name="amadeus",
        type=ChannelType.AMADEUS,
        host="gds.test",
        credentials={"enabled": True, "soap_security": "<Security/>"},
    )

    resp = _response_credential_swap_stage(
        content=b"<Envelope/>",
        response_headers={},
        keyring=_keyring(),
        ctx=_StageContext(channel=channel, max_inspect_bytes=1, trace_id=None, metrics=cast(Any, metrics)),
    )

    assert isinstance(resp, StarletteResponse)
    assert resp.status_code == 413
    assert metrics.xml_errors == [("amadeus", "oversize")]


def test_request_pii_stage_records_decrypted_tokens() -> None:
    keyring = _keyring()
    token = encrypt("secret", keyring)
    metrics = _CountingMetrics()
    channel = ChannelConfig(name="mock", type=ChannelType.TRAVELFUSION)

    outcome = _request_pii_stage(
        keyring=keyring,
        body=f"<Root><Value>{token}</Value></Root>".encode(),
        ctx=_StageContext(channel=channel, max_inspect_bytes=1024, trace_id=None, metrics=cast(Any, metrics)),
    )

    assert isinstance(outcome, tuple)
    body, decrypted = outcome
    assert b"secret" in body
    assert decrypted == 1
    assert metrics.decrypted == [("mock", 1)]


@pytest.mark.parametrize(
    ("body", "status", "reason"),
    [
        (b"<Root/>", 413, "payload_too_large"),
        (b"<broken", 502, "xml_parse_error"),
        (b"<Root><Value>ENC_bad</Value></Root>", 502, "pii_deanonymization_failed"),
    ],
)
def test_request_pii_stage_failures(body: bytes, status: int, reason: str) -> None:
    resp = _request_pii_stage(
        keyring=_keyring(),
        body=body,
        ctx=_StageContext(
            channel=ChannelConfig(name="mock", type=ChannelType.TRAVELFUSION),
            max_inspect_bytes=1 if status == 413 else 1024,
            trace_id=None,
            metrics=None,
        ),
    )

    assert isinstance(resp, StarletteResponse)
    assert resp.status_code == status
    assert resp.headers[WENRIX_ERROR_HEADER] == reason


@pytest.mark.parametrize(
    ("content", "status", "reason", "max_bytes"),
    [
        (b"<Root/>", 413, "payload_too_large", 1),
        (b"<broken", 502, "xml_parse_error", 1024),
        (b"<Root/>", 502, "pii_redaction_failed", 1024),
    ],
)
def test_response_pii_stage_failures(content: bytes, status: int, reason: str, max_bytes: int) -> None:
    ruleset = _required_missing_ruleset()
    resp = _response_pii_stage(
        keyring=_keyring(),
        rules=ruleset,
        content=content,
        ctx=_StageContext(
            channel=ChannelConfig(name="mock", type=ChannelType.TRAVELFUSION),
            max_inspect_bytes=max_bytes,
            trace_id=None,
            metrics=None,
        ),
    )

    assert isinstance(resp, StarletteResponse)
    assert resp.status_code == status
    assert resp.headers[WENRIX_ERROR_HEADER] == reason


def test_response_pii_stage_uncovered_forwards_and_records_metric() -> None:
    metrics = _CountingMetrics()
    ruleset = _person_ruleset("Other")  # no rule matches parsed operation "Search"
    content = b"<Root><Search><Name>Jane</Name></Search></Root>"

    result = _response_pii_stage(
        keyring=_keyring(),
        rules=ruleset,
        content=content,
        ctx=_StageContext(
            channel=ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION),
            max_inspect_bytes=1024,
            trace_id=None,
            metrics=cast(Any, metrics),
        ),
    )

    assert isinstance(result, bytes)
    assert b"Jane" in result  # forwarded unchanged, not blocked
    assert metrics.uncovered == [("tf", "Search")]
    assert metrics.redacted == []


def test_response_pii_stage_covered_does_not_record_uncovered() -> None:
    metrics = _CountingMetrics()
    ruleset = _person_ruleset("Search")  # rule matches parsed operation "Search"
    content = b"<Root><Search><Name>Jane</Name></Search></Root>"

    result = _response_pii_stage(
        keyring=_keyring(),
        rules=ruleset,
        content=content,
        ctx=_StageContext(
            channel=ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION),
            max_inspect_bytes=1024,
            trace_id=None,
            metrics=cast(Any, metrics),
        ),
    )

    assert isinstance(result, bytes)
    assert metrics.uncovered == []
    assert metrics.redacted == [("tf", {"person": 1})]


def test_response_pii_stage_records_invalid_xpath_rule_id() -> None:
    metrics = _CountingMetrics()
    ruleset = RuleSet.model_validate(
        {
            "schema_version": "1.0",
            "rules_version": "t",
            "rules": [
                {
                    "id": "tf.invalid-prefix",
                    "channel": "travelfusion",
                    "operation": "^Search$",
                    "path": "//missing:Name",
                    "pii_type": "person",
                    "method": "encrypt",
                }
            ],
        }
    )

    result = _response_pii_stage(
        keyring=_keyring(),
        rules=ruleset,
        content=b"<Root><Search><Name>Jane</Name></Search></Root>",
        ctx=_StageContext(
            channel=ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION),
            max_inspect_bytes=1024,
            trace_id=None,
            metrics=cast(Any, metrics),
        ),
    )

    assert isinstance(result, bytes)
    assert metrics.path_errors == [("tf", "tf.invalid-prefix")]


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "PATCH"])
def test_forward_supports_common_methods(method: str, travelfusion_client: TravelFusionClientFactory) -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    with travelfusion_client(httpx.MockTransport(handler)) as client:
        client.request(method, "/channel/tf/op")

    assert captured["req"].method == method


def test_debug_mode_logs_full_request_and_response_body(
    monkeypatch: pytest.MonkeyPatch,
    travelfusion_client: TravelFusionClientFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # ``create_app`` (invoked by the ``travelfusion_client`` fixture) rebinds Loguru's sink to
    # the live ``sys.stderr`` via ``configure_logging``; capsys must already be active for that
    # sink to land in captured output, so read it after the request via ``capsys.readouterr()``.
    monkeypatch.setenv("RELAY_DEBUG_MODE", "true")
    upstream_body = b"<Response><Fare>123</Fare></Response>"
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=upstream_body, headers={"content-type": "application/xml"})
    )

    with travelfusion_client(transport) as client:
        resp = client.post(
            "/channel/tf/op",
            content=b"<Search><Name>Jane</Name></Search>",
            headers={"content-type": "application/xml", "x-wenrix-trace-id": "trace-debug"},
        )

    assert resp.status_code == 200
    output = capsys.readouterr().err
    assert "<Search><Name>Jane</Name></Search>" in output
    assert "<Response><Fare>123</Fare></Response>" in output
    assert "trace-debug" in output
    assert '"direction": "request"' in output
    assert '"direction": "response"' in output


def test_debug_mode_off_by_default_does_not_log_body(
    travelfusion_client: TravelFusionClientFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b"<Ok/>"))

    with travelfusion_client(transport) as client:
        client.post(
            "/channel/tf/op",
            content=b"<TopSecretPassport>X1234567</TopSecretPassport>",
            headers={"content-type": "application/xml"},
        )

    assert "TopSecretPassport" not in capsys.readouterr().err


def test_debug_mode_logs_decoded_body_for_gzipped_request(
    monkeypatch: pytest.MonkeyPatch,
    relay_client_factory: RelayClientFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A gzip-encoded request must be logged as readable XML, not the compressed wire bytes."""
    monkeypatch.setenv("RELAY_DEBUG_MODE", "true")
    monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, pii={"enabled": True})
    original_xml = b"<Search><Name>Jane</Name></Search>"
    gzipped_body = gzip.compress(original_xml)
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=b"<Ok/>", headers={"content-type": "application/xml"})
    )

    with relay_client_factory(channel, transport) as client:
        resp = client.post(
            "/channel/tf/op",
            content=gzipped_body,
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    assert resp.status_code == 200
    output = capsys.readouterr().err
    assert "<Search><Name>Jane</Name></Search>" in output
    assert gzipped_body.decode("latin-1") not in output


def test_debug_mode_trims_oversized_body(
    monkeypatch: pytest.MonkeyPatch,
    travelfusion_client: TravelFusionClientFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RELAY_DEBUG_MODE", "true")
    monkeypatch.setenv("RELAY_DEBUG_MODE_MAX_BODY_BYTES", "16")
    big_body = b"<Search>" + b"x" * 100 + b"</Search>"
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b"<Ok/>"))

    with travelfusion_client(transport) as client:
        client.post("/channel/tf/op", content=big_body, headers={"content-type": "application/xml"})

    output = capsys.readouterr().err
    assert f"truncated, {len(big_body)} bytes total" in output
    assert "x" * 100 not in output
