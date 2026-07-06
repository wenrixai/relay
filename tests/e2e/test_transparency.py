"""Item 1 — transparency: the channel never sees Wenrix/forwarding/hop-by-hop headers, ``Host`` is
rewritten to the channel, no ``Server`` header reaches the client; plus a no-credential-swap channel
relays the body byte-for-byte.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, RecordingUpstream, make_channel

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
    upstream = RecordingUpstream()
    channel = make_channel(gds, credentialed=True, pii_enabled=True)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post(f"/channel/{gds.name}/op", content=gds.request_body(), headers=_HOSTILE)

    assert response.status_code == 200
    assert len(upstream.headers) == 1
    forwarded = {k.lower() for k in upstream.headers[-1]}
    for banned in _MUST_NOT_APPEAR:
        assert banned not in forwarded, f"{banned} leaked to channel"
    # The Connection-named token header is also stripped.
    assert "x-secret" not in forwarded
    # Host rewritten to the channel; nothing added on the forwarding front.
    assert upstream.headers[-1]["host"] == gds.host
    for added in ("via", "forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"):
        assert added not in forwarded
    # No Server header on the client response.
    assert "server" not in {k.lower() for k in response.headers}


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_no_credential_swap_passthrough(gds: Gds, e2e_client: E2EClientFactory) -> None:
    """A channel with no credentials and PII disabled relays the body verbatim (no inspection)."""
    opaque_body = b"\x00\x01\x02 not-xml payload \xff\xfe"
    upstream = RecordingUpstream(response=b"\x10\x20 opaque-reply \x30")
    channel = make_channel(gds, credentialed=False, pii_enabled=False)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post(
            f"/channel/{gds.name}/op",
            content=opaque_body,
            headers={"content-type": "application/octet-stream"},
        )

    assert response.status_code == 200
    # Body crosses to the channel byte-for-byte — no mutation, no ENC_ tokens.
    assert upstream.bodies[-1] == opaque_body
    assert b"ENC_" not in upstream.bodies[-1]
    # Response returned to the client unchanged, no Server header.
    assert response.content == b"\x10\x20 opaque-reply \x30"
    assert "server" not in {k.lower() for k in response.headers}
    # Host still rewritten even on the pure pass-through path.
    assert upstream.headers[-1]["host"] == gds.host
