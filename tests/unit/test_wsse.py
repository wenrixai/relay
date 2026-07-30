"""WS-Security UsernameToken builder (fix #4).

`_PASSWORD` is the input half of a fixed password-digest test vector, not a credential — the test
asserts `password_digest()` reproduces `_EXPECTED_DIGEST` for a known nonce/created pair. Snyk Code
flags it as CWE-798; the justification and exclusion live in `.snyk`.
"""

from __future__ import annotations

import base64
import hashlib

from channel_relay.channels.wsse import (
    PASSWORD_DIGEST_TYPE,
    PASSWORD_TEXT_TYPE,
    PASSWORD_TYPE_DIGEST,
    PASSWORD_TYPE_TEXT,
    build_username_token_security,
    password_digest,
)
from channel_relay.pii.xml_ops import parse_bytes

# Fixed vector: nonce = 0x00..0f, created below, password "S3cret!".
_NONCE = bytes(range(16))
_CREATED = "2026-07-06T12:00:00Z"
_PASSWORD = "S3cret!"
_EXPECTED_DIGEST = "drCT89qwRBm8TpK3Fjfs+w0vQmY="


def test_password_digest_matches_amadeus_variant() -> None:
    assert password_digest(_PASSWORD, _NONCE, _CREATED) == _EXPECTED_DIGEST
    # Independent recomputation of the documented formula.
    inner = hashlib.sha1(_PASSWORD.encode()).digest()  # noqa: S324
    expected = base64.b64encode(hashlib.sha1(_NONCE + _CREATED.encode() + inner).digest()).decode()  # noqa: S324
    assert password_digest(_PASSWORD, _NONCE, _CREATED) == expected


def _child_text(root: object, local: str) -> str:
    return next(node.text or "" for node in root.iter("*") if node.tag.endswith(f"}}{local}"))


def _child_attr(root: object, local: str, attr: str) -> str:
    node = next(node for node in root.iter("*") if node.tag.endswith(f"}}{local}"))
    return node.get(attr) or ""


def test_build_digest_fragment_structure() -> None:
    fragment = build_username_token_security(
        username="1000001",
        password=_PASSWORD,
        password_type=PASSWORD_TYPE_DIGEST,
        nonce=_NONCE,
        created=_CREATED,
    )
    root = parse_bytes(fragment.encode())
    assert root.tag.endswith("}Security")
    assert _child_text(root, "Username") == "1000001"
    assert _child_attr(root, "Password", "Type") == PASSWORD_DIGEST_TYPE
    assert _child_text(root, "Password") == _EXPECTED_DIGEST
    assert _child_text(root, "Nonce") == base64.b64encode(_NONCE).decode()
    assert _child_attr(root, "Nonce", "EncodingType").endswith("#Base64Binary")
    assert _child_text(root, "Created") == _CREATED


def test_build_text_fragment_uses_plaintext() -> None:
    fragment = build_username_token_security(
        username="u",
        password=_PASSWORD,
        password_type=PASSWORD_TYPE_TEXT,
        nonce=_NONCE,
        created=_CREATED,
    )
    root = parse_bytes(fragment.encode())
    assert _child_attr(root, "Password", "Type") == PASSWORD_TEXT_TYPE
    assert _child_text(root, "Password") == _PASSWORD


def test_username_is_escaped() -> None:
    fragment = build_username_token_security(
        username="a&b<c>",
        password=_PASSWORD,
        password_type=PASSWORD_TYPE_DIGEST,
        nonce=_NONCE,
        created=_CREATED,
    )
    # Well-formed despite special chars, and round-trips to the original value.
    root = parse_bytes(fragment.encode())
    assert _child_text(root, "Username") == "a&b<c>"
