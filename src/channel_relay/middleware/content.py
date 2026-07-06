"""Content handling and classification (§5.4).

Slice 1 needs no body inspection (no PII/credential swap yet), so bodies — including
gzip/deflate and chunked — pass through transparently. When inspection *is* required, the
inspectable-body cap is enforced (oversize → 413) and the body is classified for logging.
Actual XML/JSON parsing arrives in later slices; here we only classify and log.
"""

from __future__ import annotations

from enum import StrEnum

from channel_relay.channels import credentials_require_body_inspection, credentials_require_response_keyring
from channel_relay.config.models import ChannelConfig


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
