"""Item 2 — PII fail-closed: no plaintext PII ever survives to the client, and a request carrying a
malformed ``ENC_`` token is rejected 502 without any body reaching the channel.
"""

from __future__ import annotations

import pytest

from tests.conftest import ProxyErrorAssertion
from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, assert_pii_markers_absent, post_gds_request

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_response_pii_fully_absent(gds: Gds, e2e_client: E2EClientFactory) -> None:
    """Adversarial byte-scan: every known plaintext PII marker is gone; tokens present; non-PII kept."""
    exchange = post_gds_request(e2e_client, gds, upstream_response=gds.pii_response())
    response = exchange.response

    assert response.status_code == 200
    assert_pii_markers_absent(response, gds, message="plaintext PII {marker!r} leaked to client")
    assert b"ENC_" in response.content
    assert gds.non_pii_marker in response.content


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_bad_token_request_fails_closed(
    gds: Gds,
    e2e_client: E2EClientFactory,
    assert_proxy_error: ProxyErrorAssertion,
) -> None:
    """A malformed full-match ENC_ token in the request → 502 pii_deanonymization_failed, not forwarded."""
    # No credentials: isolate the de-anonymization stage (it runs before any credential swap).
    exchange = post_gds_request(
        e2e_client,
        gds,
        content=gds.bad_token_envelope,
        headers={"x-wenrix-trace-id": "trace-badtok"},
        credentialed=False,
        pii_enabled=True,
    )
    response = exchange.response

    assert_proxy_error(response, 502, "pii_deanonymization_failed", "trace-badtok")
    # The core guarantee: the partially processed request never reached the channel.
    assert exchange.upstream.bodies == []
    assert exchange.upstream.headers == []
    # And no PII/token detail leaks into the error body.
    assert b"ENC_AAAA" not in response.content
