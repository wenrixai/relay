"""Item 4 — content-gated credential swap: a request with no SOAP Security element (e.g. an Amadeus
stateful non-start request whose session lives outside Security) is forwarded unchanged rather than
failing closed. The swap is a no-op and injects no credentials, so nothing is leaked either way.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, RecordingUpstream, make_channel

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_missing_security_header_is_forwarded_unchanged(
    gds: Gds,
    e2e_client: E2EClientFactory,
) -> None:
    upstream = RecordingUpstream()
    # Credentialed, PII off: isolate the request credential-swap stage.
    channel = make_channel(gds, credentialed=True, pii_enabled=False)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post(
            f"/channel/{gds.name}/op",
            content=gds.no_security_envelope,
            headers={"content-type": "text/xml", "x-wenrix-trace-id": "trace-swap"},
        )

    assert response.status_code == 200
    # No-op swap: the request reaches the channel with no credential fragment injected.
    assert len(upstream.bodies) == 1
    assert b"RELAY" not in upstream.bodies[0]
