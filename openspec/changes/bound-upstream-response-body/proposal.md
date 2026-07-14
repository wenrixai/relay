# Bound the upstream response body (DoS from a compromised channel)

## Why

The request path was deliberately hardened: `content.py:_bounded_inflate` caps decompression at
`max_inspect_bytes` and rejects oversize before materializing the body. The **response** path has no
equivalent. `proxy/forwarder.py` does `content = upstream.content`, which reads the entire upstream
response into memory, and httpx transparently inflates a `Content-Encoding: gzip/deflate/br` response
with no ceiling. The redaction stage's `parse_bytes(max_bytes=…)` only runs **after** the full body is
already buffered, so it cannot prevent the blow-up.

The upstream channel is exactly the semi-untrusted party the relay is designed to hide from. A
malicious or compromised channel returns a small gzip bomb (or a multi-GB plain body) → the relay
OOMs / stalls. This is a real availability hole and asymmetric with the already-hardened request path.

## What Changes

- Cap the upstream response the relay buffers. For a channel that inspects the response (PII redaction
  or response credential-swap/encryption enabled), reject a body whose decoded size exceeds
  `max_inspect_bytes` with the defined error before parsing (mirroring the request-path bound).
- Apply a global response ceiling even for pass-through channels so a compressed bomb cannot OOM the
  process regardless of inspection.
- Never fully materialize an oversized decompressed body: stream/enforce the cap incrementally as on
  the request path.

## Capabilities

### Modified Capabilities
- `transparent-relay`: the inspectable-size cap and bounded decompression apply to the **response**
  body as well as the request body; an oversize upstream response is rejected rather than buffered
  unbounded.

## Impact

- `src/channel_relay/proxy/forwarder.py`: bound the `upstream.content` read (stream + cap), reject
  oversize before redaction/credential stages.
- `src/channel_relay/middleware/content.py`: reuse/extend the bounded-decode helper for the response
  direction if needed.
- `tests/unit/test_forwarder.py`, `tests/integration/`: a small gzip-bomb upstream response on an
  inspected channel → rejected (not OOM); a plain oversize response → rejected; normal responses
  unaffected.
