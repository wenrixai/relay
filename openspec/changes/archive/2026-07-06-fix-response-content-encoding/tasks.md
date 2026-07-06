## 1. Header hygiene

- [x] 1.1 `tests/unit/test_header_hygiene.py`: failing test — `clean_response_headers` drops
      `content-encoding`
- [x] 1.2 `src/channel_relay/middleware/header_hygiene.py`: add `"content-encoding"` to the
      `clean_response_headers` drop set

## 2. Forwarder integration

- [x] 2.1 `tests/integration/test_response_content_encoding.py`: failing test — a gzipped upstream XML
      response on a channel where no stage mutates the body reaches the client with a decodable body
      and **no** `Content-Encoding` header
- [x] 2.2 Confirm the mutation paths (credential swap, PII redaction) still return a correct,
      decodable body with no `Content-Encoding` (existing suites green)

## 3. Verification

- [x] 3.1 `just test-fast` green
- [x] 3.2 `just ci` green (ruff, mypy, pylint, pytest, coverage) — 345 passed, 95% coverage
