"""Content handling and classification (§5.4).

Slice 1 needs no body inspection (no PII/credential swap yet), so bodies — including
gzip/deflate and chunked — pass through transparently. When inspection *is* required, the
inspectable-body cap is enforced (oversize → 413) and the body is classified for logging.
Actual XML/JSON parsing arrives in later slices; here we only classify and log.
"""

from __future__ import annotations

import zlib
from enum import StrEnum

from channel_relay.channels import credentials_require_body_inspection, credentials_require_response_keyring
from channel_relay.config.models import ChannelConfig
from channel_relay.pii.xml_ops import XmlOversizeError, XmlParseError

# Content-Encoding values the relay decodes on ingress for inspection (§5.4).
GZIP = "gzip"
DEFLATE = "deflate"
_DECODABLE = frozenset({GZIP, DEFLATE})
_GZIP_WBITS = 16 + zlib.MAX_WBITS  # gzip framing
_ZLIB_WBITS = zlib.MAX_WBITS  # zlib-wrapped deflate
_RAW_WBITS = -zlib.MAX_WBITS  # raw deflate (some servers omit the zlib header)


class ContentKind(StrEnum):
    """Coarse payload classification for logging/metrics (§5.4)."""

    XML = "xml"
    JSON = "json"
    MTOM = "mtom"
    OPAQUE = "opaque"


def classify_content(content_type: str | None) -> ContentKind:
    """Classify a payload by its ``Content-Type`` (no body parsing)."""
    if not content_type:
        return ContentKind.OPAQUE
    ct = content_type.split(";", 1)[0].strip().lower()
    if "xop+xml" in ct or ct.startswith("multipart/related"):
        return ContentKind.MTOM
    if ct.endswith("/xml") or ct.endswith("+xml"):
        return ContentKind.XML
    if ct.endswith("/json") or ct.endswith("+json"):
        return ContentKind.JSON
    return ContentKind.OPAQUE


def requires_inspection(channel: ChannelConfig) -> bool:
    """Whether the relay must read/parse the body for this channel.

    PII-enabled channels require inspection for request de-anonymization/response
    redaction. Slice 3 credential swap adds body inspection for channels whose
    configured credentials require structural XML mutation or response auth encryption.
    Operation authorization adds body inspection for channels with a configured
    allow-list, so the inspectable-body size cap applies uniformly.
    """
    return (
        channel.pii.enabled
        or credentials_require_body_inspection(channel)
        or credentials_require_response_keyring(channel)
        or channel.operation_authorization_enabled
    )


def body_exceeds_cap(size: int, max_bytes: int) -> bool:
    """True when a body requiring inspection exceeds the inspectable-size cap (§9.4)."""
    return size > max_bytes


def is_decodable_encoding(content_encoding: str | None) -> bool:
    """True when the relay knows how to decode this ``Content-Encoding`` for inspection."""
    return (content_encoding or "").strip().lower() in _DECODABLE


def _bounded_inflate(data: bytes, wbits: int, max_bytes: int) -> bytes:
    """Incrementally inflate ``data`` under ``wbits``, rejecting decompressed oversize.

    Never materializes more than ``max_bytes`` (+1) before raising, so a small compressible
    body cannot expand to gigabytes in memory (§9.4). Raises the raw zlib/EOF error on a
    malformed/truncated stream for the caller to classify.
    """
    obj = zlib.decompressobj(wbits)
    out = bytearray(obj.decompress(data, max_bytes + 1))
    while obj.unconsumed_tail:
        if len(out) > max_bytes:
            raise XmlOversizeError(f"decompressed body exceeds cap {max_bytes}")
        out += obj.decompress(obj.unconsumed_tail, max_bytes + 1)
    out += obj.flush()
    if len(out) > max_bytes:
        raise XmlOversizeError(f"decompressed body exceeds cap {max_bytes}")
    return bytes(out)


def decode_body(body: bytes, content_encoding: str | None, max_bytes: int) -> bytes:
    """Decode a gzip/deflate request body for inspection, bounded by ``max_bytes``.

    Raises:
        XmlOversizeError: the decompressed body would exceed the cap (caller → 413).
        XmlParseError: the body is not a valid stream for its declared encoding, including a
            truncated stream (caller → 502 ``xml_parse_error``).
    """
    enc = (content_encoding or "").strip().lower()
    wbits_candidates: tuple[int, ...]
    if enc == GZIP:
        wbits_candidates = (_GZIP_WBITS,)
    elif enc == DEFLATE:
        wbits_candidates = (_ZLIB_WBITS, _RAW_WBITS)  # try zlib-wrapped, then raw
    else:
        return body
    # XmlOversizeError from _bounded_inflate is not a (zlib.error, OSError, EOFError), so it
    # propagates straight out (→ 413); only genuine decode failures are retried/classified here.
    last_error: Exception | None = None
    for wbits in wbits_candidates:
        try:
            return _bounded_inflate(body, wbits, max_bytes)
        except (zlib.error, OSError, EOFError) as exc:  # truncated/malformed stream
            last_error = exc
    raise XmlParseError(f"undecodable {enc} body") from last_error


def encode_body(body: bytes, content_encoding: str | None) -> bytes:
    """Re-encode a decoded body to its original ``Content-Encoding`` for egress."""
    enc = (content_encoding or "").strip().lower()
    if enc == GZIP:
        return zlib.compress(body, wbits=_GZIP_WBITS)
    if enc == DEFLATE:
        return zlib.compress(body)
    return body
