"""Item 4 — content-gated credential swap: a request with no SOAP Security element (e.g. an Amadeus
stateful non-start request whose session lives outside Security) is forwarded unchanged rather than
failing closed. The swap is a no-op and injects no credentials, so nothing is leaked either way.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, post_gds_request

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_missing_security_header_is_forwarded_unchanged(
    gds: Gds,
    e2e_client: E2EClientFactory,
) -> None:
    # Credentialed, PII off: isolate the request credential-swap stage.
    exchange = post_gds_request(
        e2e_client,
        gds,
        content=gds.no_security_envelope,
        headers={"x-wenrix-trace-id": "trace-swap"},
        credentialed=True,
        pii_enabled=False,
    )

    assert exchange.response.status_code == 200
    # No-op swap: the request reaches the channel with no credential fragment injected.
    assert len(exchange.upstream.bodies) == 1
    assert b"RELAY" not in exchange.upstream.bodies[0]
