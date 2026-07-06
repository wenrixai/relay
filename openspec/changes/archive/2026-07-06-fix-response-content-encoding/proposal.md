## Why

The relay serves `upstream.content`, which httpx has **already decompressed**, but the response
header hygiene keeps the upstream `Content-Encoding` header. When no response stage mutates the body
— a non-XML response, or a credentialed Sabre/Amadeus response that carries no auth token and
matches no PII rule — the client receives the **decoded** body still labelled
`Content-Encoding: gzip` and fails to decode it. This breaks otherwise-valid GDS responses.

Today `Content-Encoding` is only stripped on the two mutation paths (credential swap via
`_remove_body_framing(..., remove_encoding=True)`, and PII redaction via `_BODY_SENSITIVE_HEADERS`).
The passthrough path has no such strip and no test coverage.

## What Changes

- `clean_response_headers` SHALL drop `Content-Encoding` unconditionally, exactly as it already
  drops `Content-Length`. Because httpx auto-decodes `.content` for every response the relay reads,
  the upstream `Content-Encoding` value never matches the bytes the relay forwards, so it must never
  be relayed. The response body is served as identity.
- This makes the response-path `remove_encoding=True` / `_BODY_SENSITIVE_HEADERS` deletions in
  `forwarder.py` redundant; they are left in place (harmless) to avoid an over-broad refactor.

### Accepted limitation

httpx auto-decodes `gzip`/`deflate` (and `br` only if the optional Brotli lib is installed). For a
passthrough channel whose upstream returns an encoding httpx cannot decode, `.content` stays
compressed and dropping the header would be wrong — but inspectable channels already fail closed
(502 `xml_parse_error`) on such bodies at parse time, and the relay does not advertise its own
`Accept-Encoding`. This is an accepted edge, not a regression.

## Capabilities

### Modified Capabilities
- `header-hygiene`: response header cleaning SHALL additionally strip `Content-Encoding` so the
  decoded body the relay serves is never mislabelled.

## Impact

- `src/channel_relay/middleware/header_hygiene.py`: add `"content-encoding"` to the
  `clean_response_headers` drop set.
- Tests: `tests/unit/test_header_hygiene.py` (unit assertion) and a forwarder integration test for a
  gzipped, unmutated upstream response.
