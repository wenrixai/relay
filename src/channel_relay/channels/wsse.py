"""WS-Security UsernameToken construction for dynamic SOAP auth (Amadeus stateless).

Builds a fresh ``Security`` header per request with a random ``Nonce``, current ``Created``
timestamp, and a password digest. Amadeus WSAP uses the digest variant with an inner hash of the
password: ``Base64(SHA1(nonce ‖ created ‖ SHA1(password)))``.

The SHA-1 here is mandated by the WS-Security UsernameToken profile — it is a protocol digest, not
part of the relay's field cryptography. Fragments are built with lxml so username/password values are
correctly escaped; the caller re-validates the fragment through the hardened parser before insertion.
"""

from __future__ import annotations

import base64
import hashlib

from lxml import etree

# OASIS 2004 WS-Security namespaces and UsernameToken-profile type URIs (Amadeus WSAP defaults).
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
_PROFILE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0"
_MSG_SEC = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0"
PASSWORD_DIGEST_TYPE = f"{_PROFILE}#PasswordDigest"
PASSWORD_TEXT_TYPE = f"{_PROFILE}#PasswordText"
NONCE_ENCODING_TYPE = f"{_MSG_SEC}#Base64Binary"

PASSWORD_TYPE_DIGEST = "digest"
PASSWORD_TYPE_TEXT = "text"


def password_digest(password: str, nonce: bytes, created: str) -> str:
    """Amadeus WSAP UsernameToken digest: ``Base64(SHA1(nonce ‖ created ‖ SHA1(password)))``."""
    inner = hashlib.sha1(password.encode()).digest()  # noqa: S324 - WS-Security profile mandates SHA-1
    outer = hashlib.sha1(nonce + created.encode() + inner).digest()  # noqa: S324 - protocol digest
    return base64.b64encode(outer).decode()


def build_username_token_security(  # pylint: disable=too-many-arguments
    *,
    username: str,
    password: str,
    password_type: str,
    nonce: bytes,
    created: str,
    wsse_ns: str = WSSE_NS,
    wsu_ns: str = WSU_NS,
) -> str:
    """Return a serialized ``wsse:Security`` UsernameToken fragment.

    ``password_type`` is :data:`PASSWORD_TYPE_DIGEST` (Amadeus digest) or
    :data:`PASSWORD_TYPE_TEXT` (plaintext); both carry a fresh ``Nonce`` and ``Created``.
    """
    nsmap = {"wsse": wsse_ns, "wsu": wsu_ns}
    security = etree.Element(f"{{{wsse_ns}}}Security", nsmap=nsmap)
    token = etree.SubElement(security, f"{{{wsse_ns}}}UsernameToken")
    etree.SubElement(token, f"{{{wsse_ns}}}Username").text = username
    password_el = etree.SubElement(token, f"{{{wsse_ns}}}Password")
    if password_type == PASSWORD_TYPE_DIGEST:
        password_el.set("Type", PASSWORD_DIGEST_TYPE)
        password_el.text = password_digest(password, nonce, created)
    else:
        password_el.set("Type", PASSWORD_TEXT_TYPE)
        password_el.text = password
    nonce_el = etree.SubElement(token, f"{{{wsse_ns}}}Nonce")
    nonce_el.set("EncodingType", NONCE_ENCODING_TYPE)
    nonce_el.text = base64.b64encode(nonce).decode()
    etree.SubElement(token, f"{{{wsu_ns}}}Created").text = created
    return etree.tostring(security).decode()
