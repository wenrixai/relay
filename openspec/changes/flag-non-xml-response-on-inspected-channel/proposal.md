# Surface (don't silently skip) a non-XML response on an inspected channel

## Why

Response PII redaction (`_response_pii_stage`) and response credential encryption
(`_response_credential_swap_stage`) are gated on `response_kind is ContentKind.XML`, and
`response_kind` is derived **solely from the upstream `Content-Type`** (`content.py:classify_content`,
which maps `multipart/related` / `xop+xml` → `MTOM` and everything else → `OPAQUE`).

If a channel that is configured to redact PII or encrypt session credentials returns SOAP-bearing
content under an MTOM or otherwise non-`/xml` content type, **both** stages are silently skipped:
Sabre `BinarySecurityToken` / Amadeus `SessionId`,`SecurityToken` / Travelport `SessionKey` and
passenger PII pass downstream in **plaintext**, with no metric and no log. The upstream chooses the
label, so a compromised channel can suppress redaction just by mislabeling its response.

## What Changes

- When a channel with response inspection enabled (PII redaction or response credential
  swap/encryption) returns a response the relay classifies as non-XML, the relay SHALL emit a metric
  and a warning log recording the coverage bypass, rather than skipping silently. XOP/MTOM messages
  SHALL be flagged specifically (§5.4 already calls for flagging MTOM).
- Where feasible, the relay SHALL inspect/redact the root SOAP part of an MTOM message rather than
  bypassing it wholesale (binary attachment parts remain opaque).

## Capabilities

### Modified Capabilities
- `observability`: add a metric for an inspected channel whose response was not inspected because it
  was classified non-XML (including an MTOM flag).

### Modified Capabilities
- `transparent-relay`: an inspected channel's non-XML/MTOM response is surfaced (metric + log), not
  silently forwarded unredacted; the MTOM root SOAP part is inspected where feasible.

## Impact

- `src/channel_relay/proxy/forwarder.py`: on a redaction/credential-swap channel with a non-XML
  `response_kind`, emit the metric/log; route MTOM to root-part inspection where feasible.
- `src/channel_relay/observability/metrics.py`: define the metric.
- `tests/unit/test_forwarder.py`, `tests/unit/test_observability.py`: a PII/credential channel
  returning a non-XML/MTOM SOAP response increments the metric and logs; XML responses unaffected.
