"""Context-path prefix stripping (relay-configuration / transparent-relay specs).

When ``RELAY_ROOT_PATH`` is set, the relay serves all its routes under that prefix. This ASGI
middleware makes the scope ASGI-correct regardless of how the upstream load balancer forwards the
request:

- If the LB forwards the full path (``/relay/channel/x``), the prefix is stripped from ``path`` (and
  ``raw_path``) and recorded in ``scope["root_path"]``, so the app's root-mounted routes match and
  self-referential URLs stay correct.
- If the LB already stripped the prefix (``/channel/x``), no prefix is found and the scope passes
  through untouched — the same root routes match.

Empty prefix is a no-op (today's root-only behavior, byte-for-byte). The middleware only rewrites the
path; channel matching and upstream URL construction operate on the route-captured path and are
unaffected.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send


class ContextPathMiddleware:  # pylint: disable=too-few-public-methods
    """Strip a configured context-path prefix from the request scope before routing."""

    def __init__(self, app: ASGIApp, root_path: str) -> None:
        self.app = app
        self.root_path = root_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.root_path and scope["type"] in ("http", "websocket"):
            path: str = scope.get("path", "")
            prefix = self.root_path
            if path == prefix or path.startswith(f"{prefix}/"):
                scope = dict(scope)
                scope["path"] = path[len(prefix) :] or "/"
                raw_path = scope.get("raw_path")
                if raw_path is not None:
                    scope["raw_path"] = raw_path[len(prefix.encode()) :] or b"/"
                scope["root_path"] = prefix
        await self.app(scope, receive, send)
