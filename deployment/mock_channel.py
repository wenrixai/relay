"""Minimal mock upstream channel for local compose / CI smoke tests.

Responds 200 to any method/path with a small body. Stdlib only — no dependencies — so the
mock image stays tiny. Not used by the test suite (which mocks httpx transport directly).
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    def _respond(self) -> None:
        body = b'{"mock":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
