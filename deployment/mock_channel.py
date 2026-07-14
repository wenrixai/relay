"""Minimal mock upstream channel for local compose / CI smoke tests and the perf harness.

Responds 200 to any method/path. Stdlib only — no dependencies — so the mock image stays tiny.
Not used by the test suite (which mocks httpx transport directly).

Environment:
- ``MOCK_PORT``        listen port (default 9000).
- ``MOCK_LATENCY_MS``  fixed injected upstream latency in ms (default 0). Lets the perf harness
                       isolate relay overhead from network/upstream time (PROJECT.md §13.4).
- ``MOCK_BODY_FILE``   optional path to a file whose bytes are returned as the response body
                       (e.g. a redactable XML response for the PII perf scenario).
- ``MOCK_CONTENT_TYPE`` response content type (default ``application/json``).
- ``MOCK_EXPECTED_LOGIN`` optional sanitized login whose structural presence is reported via a
                          boolean response header for the perf preflight.
- ``MOCK_EXPECTED_ROUNDTRIP`` optional sanitized plaintext marker whose presence is reported via a
                              boolean response header for the perf preflight.
"""

from __future__ import annotations

import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_LATENCY_S = int(os.environ.get("MOCK_LATENCY_MS", "0")) / 1000.0
_CONTENT_TYPE = os.environ.get("MOCK_CONTENT_TYPE", "application/json")
_EXPECTED_LOGIN = os.environ.get("MOCK_EXPECTED_LOGIN")
_EXPECTED_ROUNDTRIP = os.environ.get("MOCK_EXPECTED_ROUNDTRIP")


def _load_body() -> bytes:
    body_file = os.environ.get("MOCK_BODY_FILE")
    if body_file and Path(body_file).is_file():
        return Path(body_file).read_bytes()
    return b'{"mock":"ok"}'


_BODY = _load_body()


class _Handler(BaseHTTPRequestHandler):
    def _request_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length else b""

    def _respond(self) -> None:
        request_body = self._request_body()
        if _LATENCY_S > 0:
            time.sleep(_LATENCY_S)
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPE)
        self.send_header("Content-Length", str(len(_BODY)))
        if _EXPECTED_LOGIN is not None:
            swapped = f"<LoginId>{_EXPECTED_LOGIN}</LoginId>".encode() in request_body
            self.send_header("X-Perf-Mock-Saw-Swapped-Credentials", str(swapped).lower())
        if _EXPECTED_ROUNDTRIP is not None:
            restored = _EXPECTED_ROUNDTRIP.encode() in request_body
            self.send_header("X-Perf-Mock-Saw-Roundtrip-Plaintext", str(restored).lower())
        self.end_headers()
        self.wfile.write(_BODY)

    # Handle the common verbs the relay forwards. Names are fixed by BaseHTTPRequestHandler.
    do_GET = _respond  # noqa: N815
    do_POST = _respond  # noqa: N815
    do_PUT = _respond  # noqa: N815
    do_DELETE = _respond  # noqa: N815
    do_PATCH = _respond  # noqa: N815

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Silence default stderr access logging.
        return


def main() -> None:
    port = int(os.environ.get("MOCK_PORT", "9000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
