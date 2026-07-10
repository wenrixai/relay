"""Item 1 — transparency: the channel never sees Wenrix/forwarding/hop-by-hop headers, ``Host`` is
rewritten to the channel, no ``Server`` header reaches the client; plus a no-credential-swap channel
relays the body byte-for-byte.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, assert_no_server_header, post_gds_request

pytestmark = pytest.mark.e2e

# Headers the client sends that must NOT reach the channel.
_HOSTILE = {
    "Connection": "x-secret",
    "x-secret": "leak-me",
    "Keep-Alive": "timeout=5",
    "Transfer-Encoding": "chunked",
    "X-Forwarded-For": "203.0.113.7",
    "X-Real-IP": "203.0.113.7",
    "Forwarded": "for=203.0.113.7",
    "Via": "1.1 proxy",
    "Proxy-Authorization": "Basic zzz",
    "x-wenrix-trace-id": "trace-xyz",
    "content-type": "text/xml",
}
_MUST_NOT_APPEAR = (
    "x-secret",
    "keep-alive",
    "transfer-encoding",
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
    "via",
    "proxy-authorization",
    "x-wenrix-trace-id",
)


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_hostile_headers_stripped_and_host_rewritten(gds: Gds, e2e_client: E2EClientFactory) -> None:
    exchange = post_gds_request(e2e_client, gds, headers=_HOSTILE)

    assert exchange.response.status_code == 200
    assert len(exchange.upstream.headers) == 1
    forwarded = {k.lower() for k in exchange.upstream.headers[-1]}
    for banned in _MUST_NOT_APPEAR:
        assert banned not in forwarded, f"{banned} leaked to channel"
    # The Connection-named token header is also stripped.
    assert "x-secret" not in forwarded
    # Host rewritten to the channel; nothing added on the forwarding front.
    assert exchange.upstream.headers[-1]["host"] == gds.host
    for added in ("via", "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"):
        assert added not in forwarded
    # No Server header on the client response.
    assert_no_server_header(exchange.response)


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_no_credential_swap_passthrough(gds: Gds, e2e_client: E2EClientFactory) -> None:
    """A channel with no credentials and PII disabled relays the body verbatim (no inspection)."""
    opaque_body = b"\x00\x01\x02 not-xml payload \xff\xfe"
    exchange = post_gds_request(
        e2e_client,
        gds,
        content=opaque_body,
        headers={"content-type": "application/octet-stream"},
        credentialed=False,
        pii_enabled=False,
        upstream_response=b"\x10\x20 opaque-reply \x30",
    )

    assert exchange.response.status_code == 200
    # Body crosses to the channel byte-for-byte — no mutation, no ENC_ tokens.
    assert exchange.upstream.bodies[-1] == opaque_body
    assert b"ENC_" not in exchange.upstream.bodies[-1]
    # Response returned to the client unchanged, no Server header.
    assert exchange.response.content == b"\x10\x20 opaque-reply \x30"
    assert_no_server_header(exchange.response)
    # Host still rewritten even on the pure pass-through path.
    assert exchange.upstream.headers[-1]["host"] == gds.host
