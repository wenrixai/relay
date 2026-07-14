# Harden request-body content decoding (ordering, bounds, robustness, deflate)

## Why

The request-body decode path in `proxy/forwarder.py` has four related defects; each breaks a spec
requirement or the fail-closed rule.

1. **Authorization runs before decode.** `_authorization_stage` (forwarder ~line 161) is handed the
   raw `body` read up front; the gzip decode only happens later, inside the PII/credential-swap block
   (~line 182), which the authorization stage never reaches first. `docs/PROJECT.md` §5.4 and the
   pipeline diagram put content-decode ([4]) **before** operation-parse/authorization ([5]/[6]).
   Effect: any `Content-Encoding: gzip` request to an authorization-gated channel — even a valid,
   allowed operation — fails XML parse on the compressed bytes and gets a spurious 403/502. Gzip
   traffic to any authz-gated channel is effectively blocked.

2. **Unbounded decompression (gzip bomb).** `_gzip_decode` calls `gzip.decompress(body)`, fully
   materializing output with no ceiling, and the only size gate (`body_exceeds_cap`) measures the
   **compressed** on-wire length. A small, highly compressible body under the 8 MiB cap can expand to
   gigabytes → OOM. It also runs synchronously inside the async `forward()` coroutine, blocking the
   event loop (violates the "never block the event loop" rule).

3. **`EOFError` not caught.** `_gzip_decode` catches only `(zlib.error, OSError)`. A
   truncated-but-header-valid gzip stream raises `EOFError`, which propagates to Starlette's default
   handler → bare 500 instead of the §10 JSON error contract (`502 xml_parse_error`).

4. **`deflate` never handled.** Only `content-encoding == "gzip"` is recognized. §5.4 mandates gzip
   **and** deflate decode-on-ingress / re-encode-on-egress. A well-formed `Content-Encoding: deflate`
   body on an inspection-required channel is parsed as raw XML and always 502s.

## What Changes

- Decode the request body **once, before any inspecting stage** (authorization, de-anonymization,
  credential swap), so every inspecting stage sees plaintext. Re-encode on egress preserving the
  original `Content-Encoding`.
- Handle both `gzip` and `deflate`.
- **Bound** decompression to the inspectable-size cap: abort and return 413 once the decompressed
  size would exceed `max_inspect_bytes` (incremental decompress, no full materialization). Offload the
  CPU-bound decompress off the event loop.
- Map an undecodable/truncated encoded body (including `EOFError`) to the §10 `502 xml_parse_error`
  contract, never a bare 500.

## Capabilities

### Modified Capabilities
- `transparent-relay`: content-decode ordering, gzip+deflate symmetry, bounded decompression (413 on
  decompressed oversize), and decode-failure → contract error.
- `operation-authorization`: operation is parsed from the **decoded** body; a compressed body is
  decoded before the allow-list check.

## Impact

- `src/channel_relay/proxy/forwarder.py`: hoist decode ahead of `_authorization_stage`; bounded
  incremental decompress; `EOFError` handling; deflate support; off-loop execution.
- `src/channel_relay/middleware/content.py`: bounded decode helper(s) if factored here.
- `tests/unit/test_forwarder.py`, `tests/integration/`: gzip+deflate to authz channel decoded and
  authorized; decompressed-oversize → 413; truncated stream → 502; event-loop not blocked.
