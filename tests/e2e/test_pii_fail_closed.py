"""Item 2 — PII fail-closed: no plaintext PII ever survives to the client, and a request carrying a
malformed ``ENC_`` token is rejected 502 without any body reaching the channel.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ProxyErrorAssertion
from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, RecordingUpstream, make_channel

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_response_pii_fully_absent(gds: Gds, e2e_client: E2EClientFactory) -> None:
    """Adversarial byte-scan: every known plaintext PII marker is gone; tokens present; non-PII kept."""
    upstream = RecordingUpstream(response=gds.pii_response())
    channel = make_channel(gds, credentialed=True, pii_enabled=True)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post(
            f"/channel/{gds.name}/op", content=gds.request_body(), headers={"content-type": "text/xml"}
        )

    assert response.status_code == 200
    for marker in gds.pii_markers:
        assert marker not in response.content, f"plaintext PII {marker!r} leaked to client"
    assert b"ENC_" in response.content
    assert gds.non_pii_marker in response.content


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_bad_token_request_fails_closed(
    gds: Gds,
    e2e_client: E2EClientFactory,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    """A malformed full-match ENC_ token in the request → 502 pii_deanonymization_failed, not forwarded."""
    upstream = RecordingUpstream()
    # No credentials: isolate the de-anonymization stage (it runs before any credential swap).
    channel = make_channel(gds, credentialed=False, pii_enabled=True)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post(
            f"/channel/{gds.name}/op",
            content=gds.bad_token_envelope,
            headers={"content-type": "text/xml", "x-wenrix-trace-id": "trace-badtok"},
        )

    assert_proxy_error(response, 502, "pii_deanonymization_failed", "trace-badtok")
    # The core guarantee: the partially processed request never reached the channel.
    assert upstream.bodies == []
    assert upstream.headers == []
    # And no PII/token detail leaks into the error body.
    assert b"ENC_AAAA" not in response.content
