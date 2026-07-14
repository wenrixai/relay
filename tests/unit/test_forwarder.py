"""Tests for routing + transparent pass-through forwarding (T1.6)."""

from __future__ import annotations

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

    def record_xml_parse_error(self, channel: str, kind: str) -> None:
        self.xml_errors.append((channel, kind))

    def record_pii_decrypted(self, channel: str, count: int) -> None:
        self.decrypted.append((channel, count))

    def record_pii_redacted(self, channel: str, counts: dict[str, int]) -> None:
        self.redacted.append((channel, counts))

    def record_uncovered_operation(self, channel: str, operation: str) -> None:
        self.uncovered.append((channel, operation))


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
    channel = ChannelConfig(name="gds", type=ChannelType.TRAVELPORT, host="gds.test")

    with relay_client_factory(channel, unreachable_transport) as client:
        # Config load rejects a hostless channel; null the resolved upstream on the live config to
        # exercise the forwarder's defense-in-depth guard.
        client.app.state.config.channels[0].proxy_pass = None  # type: ignore[attr-defined]
        resp = client.get("/channel/gds/op", headers={"x-wenrix-trace-id": "trace-1"})

    assert_proxy_error(resp, 502, "internal_error", "trace-1")


def test_ndc_swap_enabled_without_credential_aborts_startup(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
) -> None:
    # A swap-enabled NDC channel missing its key now fails closed at config load (was a
    # per-request 502) — require-channel-auth-and-host-at-startup.
    channel = ChannelConfig(
        name="ba",
        type=ChannelType.BA_NDC_DIRECT,
        credentials={"enabled": True, "api_key_header": "X-Client-Key"},  # no client_key
    )

    with pytest.raises(ValueError, match="ba"):  # noqa: PT012 - raised on lifespan enter
        with relay_client_factory(channel, unreachable_transport) as client:
            client.get("/channel/ba/op")


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

    body = _request_pii_stage(
        keyring=keyring,
        body=f"<Root><Value>{token}</Value></Root>".encode(),
        ctx=_StageContext(channel=channel, max_inspect_bytes=1024, trace_id=None, metrics=cast(Any, metrics)),
    )

    assert isinstance(body, bytes)
    assert b"secret" in body
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


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE", "PATCH"])
def test_forward_supports_common_methods(method: str, travelfusion_client: TravelFusionClientFactory) -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    with travelfusion_client(httpx.MockTransport(handler)) as client:
        client.request(method, "/channel/tf/op")

    assert captured["req"].method == method


# --- Request-body content decoding (harden-request-body-decoding) ---------------------------

_AUTHZ_BODY = b"<CommandList><GetBookingDetails><X/></GetBookingDetails></CommandList>"


def _authz_channel() -> ChannelConfig:
    return ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        authorization={"enabled": True, "allowed_operations": [{"operation": "GetBookingDetails", "version": "*"}]},
    )


def test_gzip_body_is_decoded_before_authorization_and_forwarded(
    relay_client_factory: RelayClientFactory,
) -> None:
    import gzip

    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    with relay_client_factory(_authz_channel(), httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/op",
            content=gzip.compress(_AUTHZ_BODY),
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    # Decoded before the allow-list check -> authorized -> forwarded (was a spurious 403/502).
    assert resp.status_code == 200
    assert "req" in captured


def test_deflate_body_is_decoded_before_authorization_and_forwarded(
    relay_client_factory: RelayClientFactory,
) -> None:
    import zlib

    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    with relay_client_factory(_authz_channel(), httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/op",
            content=zlib.compress(_AUTHZ_BODY),
            headers={"content-type": "application/xml", "content-encoding": "deflate"},
        )

    assert resp.status_code == 200
    assert "req" in captured


def test_truncated_gzip_body_returns_xml_parse_error_not_500(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    import gzip

    # A header-valid but truncated stream raises EOFError in gzip.decompress; it must map to the
    # 502 contract, not an uncontrolled 500.
    truncated = gzip.compress(b"<CommandList>" + b"X" * 200 + b"</CommandList>")[:20]

    with relay_client_factory(_authz_channel(), unreachable_transport) as client:
        resp = client.post(
            "/channel/tf/op",
            content=truncated,
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    assert_proxy_error(resp, 502, "xml_parse_error")


def test_decoded_and_mutated_body_is_re_encoded_preserving_content_encoding(
    relay_client_factory: RelayClientFactory,
) -> None:
    import gzip

    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200)

    # Travelfusion credential swap mutates the (decoded) body; egress must re-gzip it.
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "REAL", "xml_login_id": "REALXML"},
    )
    body = b"<CommandList><GetBookingDetails><LoginId>x</LoginId><XmlLoginId>y</XmlLoginId>"
    body += b"</GetBookingDetails></CommandList>"

    with relay_client_factory(channel, httpx.MockTransport(handler)) as client:
        resp = client.post(
            "/channel/tf/op",
            content=gzip.compress(body),
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    assert resp.status_code == 200
    req = captured["req"]
    assert req.headers["content-encoding"] == "gzip"
    decoded = gzip.decompress(req.content)
    assert b"REAL" in decoded and b"REALXML" in decoded  # swapped, re-encoded upstream


def test_gzip_bomb_body_rejected_with_413(
    relay_client_factory: RelayClientFactory,
    unreachable_transport: httpx.MockTransport,
) -> None:
    import gzip

    # ~16 MiB of zeros compresses tiny but exceeds the default 8 MiB inspect cap when decoded.
    bomb = gzip.compress(b"\x00" * (16 * 1024 * 1024))
    assert len(bomb) < 8_388_608  # small on the wire

    with relay_client_factory(_authz_channel(), unreachable_transport) as client:
        resp = client.post(
            "/channel/tf/op",
            content=bomb,
            headers={"content-type": "application/xml", "content-encoding": "gzip"},
        )

    assert resp.status_code == 413
