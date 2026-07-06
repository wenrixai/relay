"""Item 4 — credential swap fails closed: when a credentialed channel gets a request missing the SOAP
Security target, the relay returns 502 credential_swap_failed and never forwards the request.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ProxyErrorAssertion
from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, RecordingUpstream, make_channel

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_missing_security_header_fails_closed(
    gds: Gds,
    e2e_client: E2EClientFactory,
    assert_proxy_error: ProxyErrorAssertion,
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

    assert_proxy_error(response, 502, "credential_swap_failed", "trace-swap")
    # Fail closed: the request must not reach the channel.
    assert upstream.bodies == []
    assert upstream.headers == []
