"""HTTP header hygiene (§9.1).

The relay is a transparent HTTP/1.1 intermediary: the channel must not detect it. Both
directions strip hop-by-hop headers (RFC 7230), and the request path additionally strips
forwarding/identity headers, all ``x-wenrix-*``, and all ``Proxy-*`` before the channel,
and rewrites ``Host``. The relay never adds ``Via``/``Forwarded``/``X-Forwarded-*``. The
response path strips hop-by-hop headers and ``Server``.
"""

from __future__ import annotations

from collections.abc import Iterable

# Hop-by-hop headers (RFC 7230), never forwarded in either direction. Lowercase.
HOP_BY_HOP: frozenset[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

# Forwarding/identity headers stripped before the channel. Lowercase.
FORWARDING: frozenset[str] = frozenset(
    {
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-real-ip",
        "forwarded",
        "via",
    }
)


def _connection_tokens(items: Iterable[tuple[str, str]]) -> set[str]:
    """Tokens named in the inbound ``Connection`` header (also hop-by-hop). Lowercase."""
    tokens: set[str] = set()
    for key, value in items:
        if key.lower() == "connection":
            tokens.update(t.strip().lower() for t in value.split(",") if t.strip())
    return tokens


def _drop_request(key: str, drop: set[str]) -> bool:
    lk = key.lower()
    return lk in drop or lk == "host" or lk.startswith("x-wenrix-") or lk.startswith("proxy-")


def clean_request_headers(
    items: Iterable[tuple[str, str]],
    channel_host: str | None,
) -> list[tuple[str, str]]:
    """Return channel-safe request headers with ``Host`` rewritten to the channel host."""
    items = list(items)
    drop = set(HOP_BY_HOP) | set(FORWARDING) | _connection_tokens(items)
    cleaned = [(k, v) for k, v in items if not _drop_request(k, drop)]
    if channel_host is not None:
        cleaned.append(("host", channel_host))
    return cleaned


def clean_response_headers(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return client-safe response headers: no hop-by-hop, no ``Server``.

    ``content-length`` is dropped so the response framework recomputes it from the body.
    """
    items = list(items)
    drop = set(HOP_BY_HOP) | _connection_tokens(items) | {"server", "content-length"}
    return [(k, v) for k, v in items if k.lower() not in drop]
