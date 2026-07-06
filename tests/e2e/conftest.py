"""Shared plumbing for the end-to-end suite.

These tests drive the real relay route (``/channel/{name}/{path}`` → auth dep → ``forward()`` →
mock upstream) and assert what actually crosses the wire. The key primitive is
:class:`RecordingUpstream`: a mock channel that records every request body and header the relay
forwards (empty lists ⇒ the upstream was never called — the fail-closed guarantee), and can raise
an injected exception to simulate an upstream timeout.

Network is always mocked (see repo instructions); no test performs a real upstream call. The baked
``rules_fallback.json`` baseline is used because ``RELAY_RULES_API_URL`` is unset.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import MetricReader

from channel_relay.config.models import ChannelConfig, ChannelPII, ChannelType, RelayConfig
from channel_relay.main import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"
# Deterministic single-epoch keyring: 32 bytes of 'A'. Matches the integration suite.
KEYRING_JSON = '{"0": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}'
# Replacement SOAP security fragment installed by the credential swap; ">RELAY<" is the marker.
SOAP_SECURITY = '<wsse:Security xmlns:wsse="http://schemas.xmlsoap.org/ws/2002/12/secext">RELAY</wsse:Security>'
_SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
_WSSE = "http://schemas.xmlsoap.org/ws/2002/12/secext"


class RecordingUpstream:
    """A mock channel that records forwarded bodies/headers, or raises to simulate a timeout."""

    def __init__(self, response: bytes = b"<ok/>", status: int = 200, raise_exc: httpx.HTTPError | None = None) -> None:
        self._response = response
        self._status = status
        self._raise_exc = raise_exc
        self.bodies: list[bytes] = []
        self.headers: list[httpx.Headers] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        # Record before raising so callers can still assert nothing forwarded on the raise path
        # (the record happens only after a full read, which a raised transport error never reaches
        # — so a raising upstream leaves ``bodies``/``headers`` empty, as intended).
        if self._raise_exc is not None:
            self._raise_exc.request = request  # httpx attaches the request when raised via a real transport
            raise self._raise_exc
        self.bodies.append(request.read())
        self.headers.append(request.headers)
        return httpx.Response(
            self._status,
            content=self._response,
            headers={"content-type": "text/xml; charset=utf-8"},
        )


@dataclass(frozen=True)
class Gds:
    """Everything a per-GDS parametrized e2e test needs."""

    name: str
    channel_type: ChannelType
    host: str
    request_fixture: str  # valid request with a SOAP Security header (swap succeeds)
    pii_response_fixture: str  # response carrying plaintext PII the relay must redact
    pii_markers: tuple[bytes, ...]  # plaintext PII that must never survive to the client
    non_pii_marker: bytes  # a non-PII value that must be preserved untouched
    no_security_envelope: bytes  # request with a Header but no Security element (swap fails closed)
    bad_token_envelope: bytes  # request whose element text is exactly a malformed ENC_ token

    def request_body(self) -> bytes:
        return (FIXTURES / self.name / self.request_fixture).read_bytes()

    def pii_response(self) -> bytes:
        return (FIXTURES / self.name / self.pii_response_fixture).read_bytes()


def _no_security(body_op: str) -> bytes:
    return (
        f'<soap-env:Envelope xmlns:soap-env="{_SOAP_ENV}">'
        "<soap-env:Header></soap-env:Header>"
        f"<soap-env:Body><{body_op}/></soap-env:Body></soap-env:Envelope>"
    ).encode()


def _bad_token(element: str) -> bytes:
    # Element text is EXACTLY "ENC_AAAA": a TOKEN_RE full-match whose base64 decodes to 3 bytes
    # (< 1 + 12), so decrypt() raises TokenError → de-anonymization fails closed.
    return (
        f'<soap-env:Envelope xmlns:soap-env="{_SOAP_ENV}" xmlns:wsse="{_WSSE}">'
        f"<soap-env:Body><{element}>ENC_AAAA</{element}></soap-env:Body></soap-env:Envelope>"
    ).encode()


SABRE = Gds(
    name="sabre",
    channel_type=ChannelType.SABRE,
    host="sabre.test",
    request_fixture="request.xml",
    pii_response_fixture="get_price_quote_response.xml",
    pii_markers=(b"TESTMSTR", b"MARY", b'lastName="TEST"'),
    non_pii_marker=b"0HAH",
    no_security_envelope=_no_security("GetReservationRQ"),
    bad_token_envelope=_bad_token("wsse:BinarySecurityToken"),
)

AMADEUS = Gds(
    name="amadeus",
    channel_type=ChannelType.AMADEUS,
    host="amadeus.test",
    request_fixture="request.xml",
    pii_response_fixture="pnr_retrieve_response.xml",
    pii_markers=(b"PARK", b"JANGBIN", b"00852-62374313", b"SEAFLY314", b"M037B6058", b"NH4144402077"),
    non_pii_marker=b"DFMJER",
    no_security_envelope=_no_security("PNR_Retrieve"),
    bad_token_envelope=_bad_token("surname"),
)

GDS_PARAMS = [pytest.param(SABRE, id="sabre"), pytest.param(AMADEUS, id="amadeus")]


def make_channel(
    gds: Gds,
    *,
    credentialed: bool = True,
    pii_enabled: bool = True,
) -> ChannelConfig:
    """Build a channel config for a GDS with/without credentials and PII."""
    credentials = {"soap_security": SOAP_SECURITY} if credentialed else {}
    return ChannelConfig(
        name=gds.name,
        type=gds.channel_type,
        host=gds.host,
        credentials=credentials,
        pii=ChannelPII(enabled=pii_enabled),
    )


@dataclass
class E2EClientFactory:
    """Builds a TestClient bound to one channel + a RecordingUpstream, with the keyring set."""

    monkeypatch: pytest.MonkeyPatch

    def __call__(
        self,
        channel: ChannelConfig,
        upstream: RecordingUpstream,
        *,
        metric_reader: MetricReader | None = None,
    ) -> TestClient:
        self.monkeypatch.setenv("RELAY_PII_KEYRING", KEYRING_JSON)
        self.monkeypatch.delenv("RELAY_RULES_API_URL", raising=False)  # force baked fallback rules
        app = create_app(
            config=RelayConfig(channels=[channel]),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)),
            metric_reader=metric_reader,
        )
        return TestClient(app)


@pytest.fixture(name="e2e_client")
def e2e_client_fixture(monkeypatch: pytest.MonkeyPatch) -> E2EClientFactory:
    """Factory: ``client = e2e_client(channel, upstream, metric_reader=...)``."""
    return E2EClientFactory(monkeypatch)
