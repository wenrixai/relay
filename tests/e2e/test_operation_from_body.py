"""Item 3 — the operation is parsed from the XML body, never from a client header. A misleading
``SOAPAction`` header does not derail operation-scoped response redaction.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import GDS_PARAMS, E2EClientFactory, Gds, assert_pii_markers_absent, post_gds_request

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("gds", GDS_PARAMS)
def test_soapaction_header_ignored(gds: Gds, e2e_client: E2EClientFactory) -> None:
    """A bogus SOAPAction header is ignored: response redaction still selects rules from the body op."""
    exchange = post_gds_request(
        e2e_client,
        gds,
        headers={"SOAPAction": "urn:BogusOperationThatMatchesNoRule"},
        upstream_response=gds.pii_response(),
    )
    response = exchange.response

    assert response.status_code == 200
    # Redaction fired despite the lying header — proof the operation came from the body, not it.
    assert_pii_markers_absent(response, gds, message="header-driven op misroute leaked {marker!r}")
    assert b"ENC_" in response.content
    # The forwarded request path is body-derived; the relay adds no operation header of its own.
    assert len(exchange.upstream.bodies) == 1
