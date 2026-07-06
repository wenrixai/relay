"""Item 3 — the operation is parsed from the XML body, never from a client header. A misleading
``SOAPAction`` header does not derail operation-scoped response redaction.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, RecordingUpstream, make_channel

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_soapaction_header_ignored(gds: Gds, e2e_client: E2EClientFactory) -> None:
    """A bogus SOAPAction header is ignored: response redaction still selects rules from the body op."""
    upstream = RecordingUpstream(response=gds.pii_response())
    channel = make_channel(gds, credentialed=True, pii_enabled=True)
    client: TestClient = e2e_client(channel, upstream)
    with client:
        response = client.post(
            f"/channel/{gds.name}/op",
            content=gds.request_body(),
            headers={"content-type": "text/xml", "SOAPAction": "urn:BogusOperationThatMatchesNoRule"},
        )

    assert response.status_code == 200
    # Redaction fired despite the lying header — proof the operation came from the body, not it.
    for marker in gds.pii_markers:
        assert marker not in response.content, f"header-driven op misroute leaked {marker!r}"
    assert b"ENC_" in response.content
    # The forwarded request path is body-derived; the relay adds no operation header of its own.
    assert len(upstream.bodies) == 1
