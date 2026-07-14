# Tasks — harden request-body content decoding

## 1. Failing tests first (TDD)

- [x] 1.1 `tests/unit/test_forwarder.py`: gzip request with an allowed operation to an authz-gated channel → decoded, authorized, forwarded (currently 403/502).
- [x] 1.2 Same for `Content-Encoding: deflate`.
- [x] 1.3 Truncated-but-header-valid gzip stream to an inspection channel → `502 xml_parse_error` + `X-Wenrix-Error` (not 500). Cover `EOFError` explicitly.
- [x] 1.4 Small highly-compressible body that decompresses past `max_inspect_bytes` → 413, without materializing the full body.
- [x] 1.5 Egress preserves the original `Content-Encoding` when the body was decoded and re-encoded.
- [x] 1.6 (If feasible) assert decompression does not block the event loop (offloaded).

## 2. Decode ordering

- [x] 2.1 Hoist body decode to run ONCE before `_authorization_stage`, threading decoded bytes through authorization → de-anonymization → credential swap; re-encode before forward.

## 3. Bounded + robust decode

- [x] 3.1 Replace `gzip.decompress` with an incremental `zlib.decompressobj`/gzip loop that aborts at `max_inspect_bytes` (raise the oversize path → 413).
- [x] 3.2 Add `deflate` decode/encode symmetric to gzip (correct wbits).
- [x] 3.3 Catch `EOFError` alongside `zlib.error`/`OSError`; map decode failure to `502 xml_parse_error`.
- [x] 3.4 Offload the CPU-bound decompress off the event loop (e.g. `asyncio.to_thread`).

## 4. Verify

- [x] 4.1 Targeted suites green.
- [x] 4.2 `openspec validate harden-request-body-decoding --strict`.
- [x] 4.3 `just ci` green.
