"""Hardened lxml parsing — the only permitted XML entry point (§9.4, D5).

Every parse of untrusted XML goes through :func:`parse_bytes`: entities/DTD/network
disabled, DOCTYPE rejected outright, a resolver that raises, and byte/depth/node limits.
Ad-hoc ``etree.fromstring`` calls elsewhere are prohibited. Exceptions carry a stable
``kind`` used as the ``xml_parse_errors_total{kind}`` metric label; oversize maps to
HTTP 413 and everything else here maps to 502 (§10.3).
"""

from __future__ import annotations

from lxml import etree

DEFAULT_MAX_BYTES = 8_388_608
DEFAULT_MAX_DEPTH = 100
DEFAULT_MAX_NODES = 100_000


class XmlOpsError(ValueError):
    """Base for hardened-parse failures. ``kind`` is the metric label."""

    kind = "error"


class XmlOversizeError(XmlOpsError):
    """Document exceeds the inspectable byte cap (maps to HTTP 413)."""

    kind = "oversize"


class XmlStructureError(XmlOpsError):
    """Forbidden or excessive structure: DOCTYPE/DTD, depth, node count (maps to 502)."""

    kind = "structure"

    def __init__(self, message: str, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


class XmlParseError(XmlOpsError):
    """Not well-formed XML (maps to 502, reason ``xml_parse_error``)."""

    kind = "malformed"


class _RaisingResolver(etree.Resolver):  # pylint: disable=too-few-public-methods
    """Deny all external resolution (belt-and-braces beside ``no_network``)."""

    # lxml invokes resolve(url, id, context) at runtime; the stubs omit ``context``.
    def resolve(  # type: ignore[override]  # pylint: disable=unused-argument
        self,
        system_url: str,
        public_id: str,
        context: object,
    ) -> None:
        """Refuse every external entity/DTD lookup."""
        msg = f"external resolution denied for {system_url!r}"
        raise XmlStructureError(msg, kind="external_entity")


def make_parser() -> etree.XMLParser:
    """A defensively configured parser; one per parse call (not thread-shared)."""
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )
    # pylint sees the class-level descriptor, not the instance registry (runtime is fine).
    parser.resolvers.add(_RaisingResolver())  # pylint: disable=no-member
    return parser


def _enforce_limits(root: etree._Element, max_depth: int, max_nodes: int) -> None:
    nodes = 0
    stack: list[tuple[etree._Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        nodes += 1
        if depth > max_depth:
            raise XmlStructureError(f"element depth exceeds {max_depth}", kind="depth")
        if nodes > max_nodes:
            raise XmlStructureError(f"node count exceeds {max_nodes}", kind="nodes")
        stack.extend((child, depth + 1) for child in element)


def parse_bytes(
    data: bytes,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> etree._Element:
    """Parse untrusted XML bytes under the hardening contract.

    Raises:
        XmlOversizeError: ``data`` exceeds ``max_bytes`` (413).
        XmlStructureError: DOCTYPE/DTD present, or depth/node limits exceeded (502).
        XmlParseError: not well-formed XML (502).
    """
    if len(data) > max_bytes:
        raise XmlOversizeError(f"document of {len(data)} bytes exceeds cap {max_bytes}")
    try:
        root = etree.fromstring(data, parser=make_parser())  # the one sanctioned call site
    except etree.XMLSyntaxError as exc:
        raise XmlParseError(f"malformed XML: {exc.msg}") from exc
    docinfo = root.getroottree().docinfo
    if docinfo.doctype or docinfo.internalDTD is not None:  # type: ignore[union-attr]
        raise XmlStructureError("DOCTYPE/DTD is not allowed", kind="doctype")
    _enforce_limits(root, max_depth, max_nodes)
    return root


def serialize(root: etree._Element) -> bytes:
    """Re-serialize preserving structure and namespace declarations (§8.2)."""
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
