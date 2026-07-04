"""PII engine: response redaction and request de-anonymization (§8.5-§8.6, T2.5/T2.6).

Redaction is rule-driven (channel + operation select rules; XPath locates nodes; the
rule's action rewrites them). De-anonymization is envelope-driven: any value that
full-matches the ``ENC_`` token contract is decrypted, no rules required — so only
``encrypt`` is reversible; ``mask``/``replace``/``remove`` are one-way.

Fail closed: every unexpected error is wrapped in :class:`RedactionError` /
:class:`DeanonymizationError` and the caller must drop the partially processed body
(502 per §10.3). Error messages never carry field values, tokens, or key material.
"""

from __future__ import annotations

from lxml import etree

from channel_relay.pii.codec import TOKEN_RE, decrypt, encrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.rules import (
    FieldRule,
    MaskAction,
    RemoveAction,
    ReplaceAction,
    RuleSet,
)
from channel_relay.pii.xml_ops import parse_bytes, serialize

_SOAP_LOCAL_ENVELOPE = "Envelope"
_SOAP_LOCAL_BODY = "Body"


class RedactionError(Exception):
    """Response redaction failed; the response must not be forwarded (§10.3)."""


class DeanonymizationError(Exception):
    """Request de-anonymization failed; the request must not be forwarded (§10.3)."""


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def parse_operation(root: etree._Element) -> str:
    """Generic body-derived operation (interim until per-channel parsers, T3.2).

    SOAP: the Body's first element child's local-name. Otherwise: the root local-name.
    Never derived from headers (§5.3, D6).
    """
    if _local_name(root) == _SOAP_LOCAL_ENVELOPE:
        for child in root:
            if isinstance(child.tag, str) and _local_name(child) == _SOAP_LOCAL_BODY:
                for operation_el in child:
                    if isinstance(operation_el.tag, str):
                        return _local_name(operation_el)
    return _local_name(root)


def _apply_action(rule: FieldRule, value: str, keyring: Keyring) -> str | None:
    """The replacement for ``value`` under this rule's action (``None`` = remove)."""
    action = rule.action
    if isinstance(action, MaskAction):
        kept = value[: action.keep_prefix]
        return kept + action.mask_char * max(len(value) - action.keep_prefix, 0)
    if isinstance(action, ReplaceAction):
        return action.replacement
    if isinstance(action, RemoveAction):
        return None
    return encrypt(value, keyring)


def _locate(root: etree._Element, rule: FieldRule) -> list[object]:
    """Evaluate the rule's XPath; unknown prefixes/invalid paths are a no-match (§9.4)."""
    try:
        result = root.xpath(rule.path, namespaces=rule.namespaces or None)
    except etree.XPathError:
        return []
    return list(result) if isinstance(result, list) else []


def _ignored(rule: FieldRule, value: str) -> bool:
    return any(pattern.search(value) for pattern in rule.ignored_re)


def _rewrite_node(node: object, rule: FieldRule, keyring: Keyring) -> bool:
    """Apply the rule's action to one located node. Returns True when a field changed."""
    if isinstance(node, etree._Element):  # pylint: disable=protected-access  # lxml's public-in-practice type
        value = node.text
        if value is None or _ignored(rule, value):
            return False
        node.text = _apply_action(rule, value, keyring)
        return True
    # Attribute results are "smart strings" carrying their owner element.
    if isinstance(node, str) and hasattr(node, "getparent"):
        parent = node.getparent()
        attrname = getattr(node, "attrname", None)
        if parent is None or attrname is None or _ignored(rule, str(node)):
            return False
        replacement = _apply_action(rule, str(node), keyring)
        if replacement is None:
            del parent.attrib[attrname]
        else:
            parent.set(attrname, replacement)
        return True
    return False


def select_rules(ruleset: RuleSet, channel: str, operation: str) -> list[FieldRule]:
    """Rules applicable to this channel + operation; jsonpath rules are deferred (O6)."""
    return [
        rule
        for rule in ruleset.rules
        if rule.path_type == "xpath" and rule.channel == channel and rule.operation_re.search(operation)
    ]


def redact_response_body(
    body: bytes,
    *,
    channel: str,
    ruleset: RuleSet,
    keyring: Keyring,
    max_bytes: int | None = None,
) -> tuple[bytes, dict[str, int]]:
    """Redact a channel response per the matching rules (§8.5).

    Returns the re-serialized body and per-``pii_type`` counts of actioned fields.

    Raises:
        XmlOpsError: hardened-parse failure (caller maps to 413/502 ``xml_parse_error``).
        RedactionError: any other failure; the caller must not forward the body.
    """
    kwargs = {"max_bytes": max_bytes} if max_bytes is not None else {}
    root = parse_bytes(body, **kwargs)
    counts: dict[str, int] = {}
    try:
        operation = parse_operation(root)
        for rule in select_rules(ruleset, channel, operation):
            for node in _locate(root, rule):
                if _rewrite_node(node, rule, keyring):
                    counts[rule.pii_type.value] = counts.get(rule.pii_type.value, 0) + 1
        return serialize(root), counts
    except Exception as exc:
        # Never propagate partially processed output; message carries the type only.
        msg = f"redaction failed: {type(exc).__name__}"
        raise RedactionError(msg) from exc


def deanonymize_request_body(
    body: bytes,
    *,
    keyring: Keyring,
    max_bytes: int | None = None,
) -> tuple[bytes, int]:
    """Replace every full-match ``ENC_`` token in text/attribute values (§8.6).

    Returns the re-serialized body and the number of tokens decrypted.

    Raises:
        XmlOpsError: hardened-parse failure.
        DeanonymizationError: token decode/decrypt failure; request must not forward.
    """
    kwargs = {"max_bytes": max_bytes} if max_bytes is not None else {}
    root = parse_bytes(body, **kwargs)
    decrypted = 0
    try:
        for element in root.iter("*"):  # "*" yields elements only (no comments/PIs)
            if element.text is not None and TOKEN_RE.fullmatch(element.text):
                element.text = decrypt(element.text, keyring)
                decrypted += 1
            for name, value in element.attrib.items():
                text_value = str(value)
                if TOKEN_RE.fullmatch(text_value):
                    element.set(name, decrypt(text_value, keyring))
                    decrypted += 1
        return serialize(root), decrypted
    except Exception as exc:
        msg = f"de-anonymization failed: {type(exc).__name__}"
        raise DeanonymizationError(msg) from exc
