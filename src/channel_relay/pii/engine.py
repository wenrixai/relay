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

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import assert_never

from lxml import etree

from channel_relay.pii.codec import TOKEN_RE, TokenError, decrypt, encrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.rules import (
    EncryptAction,
    FieldRule,
    MaskAction,
    ReferenceRule,
    RemoveAction,
    ReplaceAction,
    Rule,
    RuleSet,
)
from channel_relay.pii.xml_ops import parse_bytes, serialize

# Un-anchored token matcher for scanning tokens embedded within free text (§8.6). The
# base64url alphabet has no whitespace/punctuation, so each match ends at the first such
# boundary — the codec's ``TOKEN_RE`` is the anchored (full-value) form of this pattern.
_EMBEDDED_TOKEN_RE = re.compile(r"ENC_[A-Za-z0-9_-]+")

# Type alias for the collector: pii_type value → set of plaintext values seen this pass.
_Collector = dict[str, set[str]]

# Per-pass (plaintext, deterministic) → token cache: the same value encrypted under the same
# mode reuses one token within a single redaction pass, so intra-response equality survives
# tokenization. Like the collector, it lives only for one pass and is never persisted or logged.
_TokenCache = dict[tuple[str, bool], str]

_SOAP_LOCAL_ENVELOPE = "Envelope"
_SOAP_LOCAL_BODY = "Body"
_Span = tuple[int, int]


@dataclass(frozen=True)
class _RedactionCtx:
    """Per-pass state threaded through the redaction call chain (keyring, caches, mode)."""

    keyring: Keyring | None
    collector: _Collector
    token_cache: _TokenCache
    force_redact: bool
    on_namespace_miss: Callable[[], None] | None = None


@dataclass(frozen=True)
class RedactionOutcome:
    """Result of a response redaction pass.

    Exposes the redacted ``body``, per-``pii_type`` ``counts``, the parsed ``operation``, and
    whether any rule matched it (``covered``) so callers can surface a coverage-gap metric — an
    uncovered operation is still forwarded, not blocked (D1).
    """

    body: bytes
    counts: dict[str, int]
    operation: str
    covered: bool


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


_FORCE_REDACT_PLACEHOLDER = "REDACTED"


def _encrypt_cached(value: str, keyring: Keyring, deterministic: bool, token_cache: _TokenCache) -> str:
    """Encrypt via the pass-scoped cache: same (plaintext, mode) → same token within one pass."""
    key = (value, deterministic)
    token = token_cache.get(key)
    if token is None:
        token = encrypt(value, keyring, deterministic=deterministic)
        token_cache[key] = token
    return token


def _apply_action(rule: FieldRule, value: str, ctx: _RedactionCtx) -> str | None:
    """The replacement for ``value`` under this rule's action (``None`` = remove)."""
    action = rule.action
    match action:
        case MaskAction():
            kept = value[: action.keep_prefix]
            return kept + action.mask_char * max(len(value) - action.keep_prefix, 0)
        case ReplaceAction():
            return action.replacement
        case RemoveAction():
            return None
        case EncryptAction():
            if ctx.force_redact:
                return _FORCE_REDACT_PLACEHOLDER
            assert ctx.keyring is not None
            return _encrypt_cached(value, ctx.keyring, action.deterministic, ctx.token_cache)
        case _:
            assert_never(action)


def _locate(root: etree._Element, rule: FieldRule | ReferenceRule, ctx: _RedactionCtx) -> list[object]:
    """Evaluate the rule's XPath; unknown prefixes/invalid paths are a no-match (§9.4).

    A namespace/XPath failure is observable, not silent: it emits the namespace-miss metric so a
    rule-authoring typo (which yields zero redaction) is discoverable (redaction-engine spec).
    """
    try:
        result = root.xpath(rule.path, namespaces=rule.namespaces or None)
    except etree.XPathError:
        if ctx.on_namespace_miss is not None:
            ctx.on_namespace_miss()
        return []
    return list(result) if isinstance(result, list) else []


def _ignored(rule: FieldRule, value: str) -> bool:
    return any(pattern.search(value) for pattern in rule.ignored_re)


def _collect(collector: _Collector, rule: FieldRule, value: str) -> None:
    """Record a matched plaintext value under its pii_type for later reference rules."""
    collector.setdefault(rule.pii_type.value, set()).add(value)


def _span_for_match(match: re.Match[str]) -> _Span | None:
    """Return the PII span for an extraction match.

    A single capture group narrows the redaction to that group. With zero or multiple
    groups the whole match is the PII span, keeping the rule behavior unambiguous.
    """
    if match.re.groups == 1:
        start, end = match.span(1)
    else:
        start, end = match.span(0)
    if start < 0 or end <= start:
        return None
    return start, end


def _extract_spans(rule: FieldRule, value: str) -> list[_Span]:
    """Return non-overlapping extraction spans in source order."""
    spans: list[_Span] = []
    occupied: list[_Span] = []
    for pattern in rule.extract_re:
        for match in pattern.finditer(value):
            span = _span_for_match(match)
            if span is None:
                continue
            start, end = span
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            spans.append(span)
            occupied.append(span)
    return sorted(spans)


def _apply_extracted_actions(
    value: str, spans: Sequence[_Span], rule: FieldRule, ctx: _RedactionCtx
) -> tuple[str, int]:
    """Rewrite extracted spans inside ``value`` while preserving surrounding text."""
    rewritten = value
    for start, end in reversed(spans):
        plaintext = value[start:end]
        _collect(ctx.collector, rule, plaintext)
        replacement = _apply_action(rule, plaintext, ctx) or ""
        rewritten = f"{rewritten[:start]}{replacement}{rewritten[end:]}"
    return rewritten, len(spans)


def _rewrite_value(value: str, rule: FieldRule, ctx: _RedactionCtx) -> tuple[str | None, int]:
    """Apply a field rule to one text/attribute value."""
    if _ignored(rule, value):
        return value, 0
    if rule.extract_patterns:
        spans = _extract_spans(rule, value)
        if not spans:
            return value, 0
        return _apply_extracted_actions(value, spans, rule, ctx)
    _collect(ctx.collector, rule, value)
    return _apply_action(rule, value, ctx), 1


def _rewrite_node(node: object, rule: FieldRule, ctx: _RedactionCtx) -> int:
    """Apply the rule's action to one located node. Returns the number of changed fields/spans.

    The pre-rewrite plaintext is collected first, so reference rules (phase 2) can search
    free text for it even though this node is about to become a token (D4).
    """
    if isinstance(node, etree._Element):  # pylint: disable=protected-access  # lxml's public-in-practice type
        value = node.text
        if value is None:
            return 0
        replacement, count = _rewrite_value(value, rule, ctx)
        if count:
            node.text = replacement
        return count
    # Attribute results are "smart strings" carrying their owner element.
    if isinstance(node, str) and hasattr(node, "getparent"):
        parent = node.getparent()
        attrname = getattr(node, "attrname", None)
        if parent is None or attrname is None:
            return 0
        replacement, count = _rewrite_value(str(node), rule, ctx)
        if count:
            if replacement is None:
                del parent.attrib[attrname]
            else:
                parent.set(attrname, replacement)
        return count
    return 0


def select_rules(ruleset: RuleSet, channel: str, operation: str) -> list[Rule]:
    """Rules applicable to this channel + operation; jsonpath rules are deferred (O6)."""
    return [
        rule
        for rule in ruleset.rules
        if rule.path_type == "xpath" and rule.channel == channel and rule.operation_re.search(operation)
    ]


def _select_rules_for_channels(ruleset: RuleSet, channels: str | Sequence[str], operation: str) -> list[Rule]:
    """Rules for the first channel alias matching this operation."""
    if isinstance(channels, str):
        return select_rules(ruleset, channels, operation)
    for channel in channels:
        selected = select_rules(ruleset, channel, operation)
        if selected:
            return selected
    return []


def _reference_pattern(rule: ReferenceRule, values: set[str]) -> re.Pattern[str] | None:
    """A case-insensitive alternation over guarded literal values, longest-first.

    Values are ``re.escape``-d (a collected value is a literal, never a rule-supplied
    regex — D6), length-filtered, and — when ``word_boundary`` — fenced by alphanumeric
    look-arounds so "John" cannot hit "Johnson".
    """
    candidates = sorted(
        {v for v in values if len(v) >= rule.min_match_len},
        key=len,
        reverse=True,
    )
    if not candidates:
        return None
    alternation = "|".join(re.escape(v) for v in candidates)
    if rule.word_boundary:
        alternation = rf"(?<![0-9A-Za-z])(?:{alternation})(?![0-9A-Za-z])"
    return re.compile(alternation, re.IGNORECASE)


def _redact_reference_rule(
    root: etree._Element, rule: ReferenceRule, ctx: _RedactionCtx, counts: dict[str, int]
) -> None:
    """Phase 2: encrypt occurrences of collected source values inside the rule's target nodes.

    Each hit goes through the pass-scoped token cache, so a value already tokenized by a
    phase-1 field rule (or an earlier hit) reuses that token instead of a fresh IV.
    """
    values: set[str] = set()
    for pii_type in rule.source_pii_types:
        values |= ctx.collector.get(pii_type.value, set())
    pattern = _reference_pattern(rule, values)
    if pattern is None:
        return
    if not ctx.force_redact:
        assert ctx.keyring is not None
    keyring = ctx.keyring
    deterministic = rule.action.deterministic
    for node in _locate(root, rule, ctx):
        if not isinstance(node, etree._Element):  # pylint: disable=protected-access  # lxml public-in-practice
            continue
        text = node.text
        if text is None:
            continue
        if ctx.force_redact:
            new_text, hits = pattern.subn(_FORCE_REDACT_PLACEHOLDER, text)
        else:

            def _replace(m: re.Match[str]) -> str:
                assert keyring is not None
                return _encrypt_cached(m.group(0), keyring, deterministic, ctx.token_cache)

            new_text, hits = pattern.subn(_replace, text)
        if hits:
            node.text = new_text
            counts[rule.pii_type.value] = counts.get(rule.pii_type.value, 0) + hits


def _redact_field_rule(root: etree._Element, rule: FieldRule, ctx: _RedactionCtx) -> int:
    """Apply one field rule and return the number of rewritten fields/spans."""
    located = _locate(root, rule, ctx)
    if rule.required and not located:
        msg = f"required rule {rule.id!r} matched no nodes"
        raise RedactionError(msg)
    rewrites = sum(_rewrite_node(node, rule, ctx) for node in located)
    if rule.required and not rewrites:
        msg = f"required rule {rule.id!r} rewrote no values"
        raise RedactionError(msg)
    return rewrites


def redact_response(  # pylint: disable=too-many-arguments,too-many-locals
    body: bytes,
    *,
    channel: str | Sequence[str],
    ruleset: RuleSet,
    keyring: Keyring | None,
    force_redact: bool = False,
    max_bytes: int | None = None,
    operation_parser: Callable[[etree._Element], str] = parse_operation,
    namespace_miss_hook: Callable[[], None] | None = None,
) -> RedactionOutcome:
    """Redact a channel response per the matching rules (§8.5).

    Returns a :class:`RedactionOutcome` — the re-serialized body, per-``pii_type`` counts of
    actioned fields, the parsed operation, and whether any rule matched it (``covered``).
    :func:`redact_response_body` is the ``(body, counts)`` wrapper for callers that don't need
    the coverage outcome.

    ``keyring`` may be ``None`` only when ``force_redact`` is ``True`` for every selected
    ``encrypt`` action (no crypto codec call is made on that path).

    Raises:
        XmlOpsError: hardened-parse failure (caller maps to 413/502 ``xml_parse_error``).
        RedactionError: any other failure; the caller must not forward the body.
    """
    kwargs = {"max_bytes": max_bytes} if max_bytes is not None else {}
    root = parse_bytes(body, **kwargs)
    counts: dict[str, int] = {}
    ctx = _RedactionCtx(
        keyring=keyring,
        collector={},
        token_cache={},
        force_redact=force_redact,
        on_namespace_miss=namespace_miss_hook,
    )
    try:
        operation = operation_parser(root)
        selected = _select_rules_for_channels(ruleset, channel, operation)
        if not selected and operation_parser is not parse_operation:
            selected = _select_rules_for_channels(ruleset, channel, parse_operation(root))
        covered = bool(selected)
        # Phase 1: structured field rules — collect plaintext, then rewrite each node (D4).
        for rule in selected:
            if isinstance(rule, FieldRule):
                rewrites = _redact_field_rule(root, rule, ctx)
                if rewrites:
                    counts[rule.pii_type.value] = counts.get(rule.pii_type.value, 0) + rewrites
        # Phase 2: reference rules — search free text for the values collected in phase 1.
        for rule in selected:
            if isinstance(rule, ReferenceRule):
                _redact_reference_rule(root, rule, ctx, counts)
        return RedactionOutcome(serialize(root), counts, operation, covered)
    except Exception as exc:
        # Never propagate partially processed output; message carries the type only.
        msg = f"redaction failed: {type(exc).__name__}"
        raise RedactionError(msg) from exc


def redact_response_body(  # pylint: disable=too-many-arguments
    body: bytes,
    *,
    channel: str | Sequence[str],
    ruleset: RuleSet,
    keyring: Keyring | None,
    force_redact: bool = False,
    max_bytes: int | None = None,
    operation_parser: Callable[[etree._Element], str] = parse_operation,
) -> tuple[bytes, dict[str, int]]:
    """``(body, counts)`` wrapper over :func:`redact_response` (see it for full semantics)."""
    outcome = redact_response(
        body,
        channel=channel,
        ruleset=ruleset,
        keyring=keyring,
        force_redact=force_redact,
        max_bytes=max_bytes,
        operation_parser=operation_parser,
    )
    return outcome.body, outcome.counts


def _deanonymize_value(value: str, keyring: Keyring) -> tuple[str, int]:
    """Decrypt ``ENC_`` tokens in one text/attribute value; return (new_value, count).

    A value that is EXACTLY one token fails closed on a bad token (the caller raises 502);
    an embedded lookalike that will not decrypt is left untouched, because free text may
    legitimately contain an ``ENC_``-prefixed word (§8.6, D3-A).
    """
    if TOKEN_RE.fullmatch(value):
        return decrypt(value, keyring), 1  # may raise TokenError → caller fails closed
    hits = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal hits
        try:
            plaintext = decrypt(match.group(0), keyring)
        except TokenError:
            return match.group(0)  # embedded lookalike, not a real token — leave as-is
        hits += 1
        return plaintext

    return _EMBEDDED_TOKEN_RE.sub(_replace, value), hits


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
            if element.text is not None:
                element.text, hits = _deanonymize_value(element.text, keyring)
                decrypted += hits
            for name, value in element.attrib.items():
                new_value, hits = _deanonymize_value(str(value), keyring)
                if hits:
                    element.set(name, new_value)
                    decrypted += hits
        return serialize(root), decrypted
    except Exception as exc:
        msg = f"de-anonymization failed: {type(exc).__name__}"
        raise DeanonymizationError(msg) from exc
