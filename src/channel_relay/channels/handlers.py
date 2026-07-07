"""Concrete channel handlers for Slice 3 credential swap."""

# Handler method names are defined by the ChannelHandler protocol; class docstrings carry
# the supplier-specific behavior, so repeating method docstrings adds noise.
# pylint: disable=missing-function-docstring

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from lxml import etree

from channel_relay.channels.base import CredentialSwapError, SwapContext
from channel_relay.channels.wsse import (
    PASSWORD_TYPE_DIGEST,
    PASSWORD_TYPE_TEXT,
    WSSE_NS,
    WSU_NS,
    build_username_token_security,
)
from channel_relay.config.models import ChannelConfig, ChannelType
from channel_relay.pii.codec import TOKEN_RE, encrypt
from channel_relay.pii.xml_ops import parse_bytes

_NONCE_BYTES = 16

_SOAP_ENVELOPE = "Envelope"
_SOAP_HEADER = "Header"
_SOAP_BODY = "Body"
_SECURITY = "Security"
_BINARY_SECURITY_TOKEN = "BinarySecurityToken"
_USERNAME_TOKEN = "UsernameToken"


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _first_element(parent: etree._Element) -> etree._Element | None:
    for child in parent:
        if isinstance(child.tag, str):
            return child
    return None


def _soap_header(root: etree._Element) -> etree._Element | None:
    if _local_name(root) != _SOAP_ENVELOPE:
        return None
    for child in root:
        if isinstance(child.tag, str) and _local_name(child) == _SOAP_HEADER:
            return child
    return None


def _soap_body(root: etree._Element) -> etree._Element | None:
    if _local_name(root) != _SOAP_ENVELOPE:
        return None
    for child in root:
        if isinstance(child.tag, str) and _local_name(child) == _SOAP_BODY:
            return child
    return None


def _soap_operation(root: etree._Element) -> str:
    body = _soap_body(root)
    if body is None:
        return _local_name(root)
    operation = _first_element(body)
    return _local_name(operation) if operation is not None else _local_name(root)


def _find_first_by_local(root: etree._Element, local_name: str) -> etree._Element | None:
    for element in root.iter("*"):
        if _local_name(element) == local_name:
            return element
    return None


def _contains_binary_security_token(element: etree._Element) -> bool:
    """True when the security target carries a session ``BinarySecurityToken`` (Sabre reuse)."""
    return any(_local_name(node) == _BINARY_SECURITY_TOKEN for node in element.iter("*"))


def _require_credential(credentials: dict[str, str], key: str) -> str:
    value = credentials.get(key)
    if not value:
        raise CredentialSwapError(f"missing credential {key}")
    return value


def _set_header(headers: dict[str, str], name: str, value: str) -> None:
    """Set an outbound header, dropping any client-sent case variant to avoid duplicates."""
    lowered = name.lower()
    for existing in [key for key in headers if key.lower() == lowered]:
        del headers[existing]
    headers[name] = value


def _replace_with_fragment(target: etree._Element, fragment_text: str) -> None:
    try:
        replacement = parse_bytes(fragment_text.encode())
    except Exception as exc:  # noqa: BLE001 - caller maps all parse failures to swap failure
        raise CredentialSwapError("soap_security is not parseable XML") from exc
    parent = target.getparent()
    if parent is None:
        raise CredentialSwapError("SOAP security target has no parent")
    index = parent.index(target)
    parent.remove(target)
    parent.insert(index, replacement)


def _namespaces(root: etree._Element) -> dict[str, str]:
    return {prefix: uri for prefix, uri in root.nsmap.items() if prefix is not None}


def _dynamic_security_fragment(credentials: dict[str, str]) -> str:
    """Build a fresh WS-Security UsernameToken fragment for stateless SOAP auth (Amadeus).

    Generates a new nonce and UTC ``Created`` per call so the digest is never stale.
    """
    password_type = credentials.get("soap_password_type", PASSWORD_TYPE_DIGEST)
    if password_type not in {PASSWORD_TYPE_DIGEST, PASSWORD_TYPE_TEXT}:
        raise CredentialSwapError("soap_password_type must be 'digest' or 'text'")
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build_username_token_security(
        username=_require_credential(credentials, "soap_username"),
        password=_require_credential(credentials, "soap_password"),
        password_type=password_type,
        nonce=os.urandom(_NONCE_BYTES),
        created=created,
        wsse_ns=credentials.get("soap_wsse_ns", WSSE_NS),
        wsu_ns=credentials.get("soap_wsu_ns", WSU_NS),
    )


@dataclass(frozen=True, slots=True)
class NoopResponseMixin:
    """Default response hook for channels without response credential cleanup."""

    def swap_response(self, root: etree._Element, context: SwapContext) -> bool:  # pylint: disable=unused-argument
        return False

    def requires_response_keyring(self, channel: ChannelConfig) -> bool:  # pylint: disable=unused-argument
        return False


@dataclass(frozen=True, slots=True)
class NoHeaderSwapMixin:
    """Default request-header hook for channels that inject no outbound credential header."""

    def swap_request_headers(self, context: SwapContext) -> None:  # pylint: disable=unused-argument
        return None


@dataclass(frozen=True, slots=True)
class NoBodySwapMixin:
    """Default request-body hook for channels that never mutate the XML body."""

    def swap_request_body(self, root: etree._Element, context: SwapContext) -> bool:  # pylint: disable=unused-argument
        return False


@dataclass(frozen=True, slots=True)
class NoCredentialValidationMixin:
    """Default config-load validation for channels with no required credential shape."""

    def validate_credentials(self, channel: ChannelConfig) -> None:  # pylint: disable=unused-argument
        return None


@dataclass(frozen=True, slots=True)
class TravelfusionHandler(NoHeaderSwapMixin, NoCredentialValidationMixin):
    """Travelfusion XML element credential swap."""

    channel_type: ChannelType = ChannelType.TRAVELFUSION

    def parse_operation(self, root: etree._Element) -> str:
        for child in root:
            if isinstance(child.tag, str) and _local_name(child) != "GeneralInfoItemList":
                return _local_name(child)
        return _local_name(root)

    def requires_body_inspection(self, channel: ChannelConfig) -> bool:
        return bool(channel.credential_values)

    def requires_response_keyring(self, channel: ChannelConfig) -> bool:  # pylint: disable=unused-argument
        return False

    def swap_request_body(self, root: etree._Element, context: SwapContext) -> bool:
        credentials = context.channel.credential_values
        if not credentials:
            return False
        operation_name = self.parse_operation(root)
        operation = next(
            (child for child in root if isinstance(child.tag, str) and _local_name(child) == operation_name),
            None,
        )
        if operation is None:
            raise CredentialSwapError("Travelfusion operation element not found")
        login = operation.find("LoginId")
        xml_login = operation.find("XmlLoginId")
        if login is None or xml_login is None:
            raise CredentialSwapError("Travelfusion login elements not found")
        login.text = _require_credential(credentials, "login_id")
        xml_login.text = _require_credential(credentials, "xml_login_id")
        supplier_list = operation.find("CustomSupplierParameterList")
        if supplier_list is not None and credentials.get("supplier_parameters"):
            supplier_list.clear()
            for name, value in _parse_supplier_parameters(credentials["supplier_parameters"]):
                item = etree.SubElement(supplier_list, "SupplierParameter")
                etree.SubElement(item, "Name").text = name
                etree.SubElement(item, "Value").text = value
        return True

    def swap_response(self, root: etree._Element, context: SwapContext) -> bool:
        if not context.channel.credential_values:
            return False
        changed = False
        for element in list(root.iter("*")):
            if _local_name(element) not in {"LoginId", "XmlLoginId"}:
                continue
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
                changed = True
        return changed


def _parse_supplier_parameters(value: str) -> list[tuple[str, str]]:
    """Parse `a=b,c=d` supplier parameters from config."""
    pairs: list[tuple[str, str]] = []
    for item in value.split(","):
        if not item.strip():
            continue
        name, sep, param_value = item.partition("=")
        if not sep:
            raise CredentialSwapError("supplier parameter must be name=value")
        pairs.append((name.strip(), param_value.strip()))
    return pairs


@dataclass(frozen=True, slots=True)
class NdcHeaderHandler(NoBodySwapMixin, NoopResponseMixin, NoCredentialValidationMixin):
    """BA/LA direct NDC header credential swap."""

    channel_type: ChannelType
    credential_key: str
    header_name: str

    def parse_operation(self, root: etree._Element) -> str:
        return _local_name(root)

    def requires_body_inspection(self, channel: ChannelConfig) -> bool:  # pylint: disable=unused-argument
        return False

    def swap_request_headers(self, context: SwapContext) -> None:
        credentials = context.channel.credential_values
        if not credentials:
            return
        header_name = credentials.get("api_key_header", self.header_name)
        _set_header(context.headers, header_name, _require_credential(credentials, self.credential_key))


@dataclass(frozen=True, slots=True)
class FarelogixHandler(NoopResponseMixin, NoCredentialValidationMixin):
    """Farelogix tc/iden + tc/agent XML attribute credential swap."""

    channel_type: ChannelType

    def parse_operation(self, root: etree._Element) -> str:
        return _soap_operation(root)

    def requires_body_inspection(self, channel: ChannelConfig) -> bool:
        return bool(channel.credential_values)

    def swap_request_headers(self, context: SwapContext) -> None:
        credentials = context.channel.credential_values
        if not credentials:
            return
        subscription_key = credentials.get("subscription_key") or credentials.get("api_key")
        if not subscription_key:
            raise CredentialSwapError("missing Farelogix subscription key")
        _set_header(context.headers, "Ocp-Apim-Subscription-Key", subscription_key)

    def swap_request_body(self, root: etree._Element, context: SwapContext) -> bool:
        credentials = context.channel.credential_values
        if not credentials:
            return False
        iden = _find_first_by_local(root, "iden")
        agent = _find_first_by_local(root, "agent")
        if iden is None or agent is None:
            raise CredentialSwapError("Farelogix credential elements not found")
        iden.set("u", _require_credential(credentials, "username"))
        iden.set("p", _require_credential(credentials, "password"))
        iden.set("agt", _require_credential(credentials, "agent"))
        iden.set("agtpwd", _require_credential(credentials, "agent_password"))
        if credentials.get("agent_number"):
            iden.set("agy", credentials["agent_number"])
        agent.set("user", _require_credential(credentials, "agent_user"))
        return True


@dataclass(frozen=True, slots=True)
class SoapSecurityHandler(NoHeaderSwapMixin):
    """Amadeus, Sabre, and Travelport SOAP security header replacement."""

    channel_type: ChannelType
    response_auth_local_names: ClassVar[set[str]] = set()

    def parse_operation(self, root: etree._Element) -> str:
        return _soap_operation(root)

    def requires_body_inspection(self, channel: ChannelConfig) -> bool:
        return bool(channel.credential_values)

    def requires_response_keyring(self, channel: ChannelConfig) -> bool:
        return self.channel_type in {ChannelType.AMADEUS, ChannelType.SABRE} and bool(channel.credential_values)

    def validate_credentials(self, channel: ChannelConfig) -> None:
        """Config-load check: a swap-enabled SOAP channel must configure exactly one auth form.

        Valid forms are a static ``soap_security`` fragment, or the complete dynamic pair
        ``soap_username``+``soap_password``. A partial dynamic config (only one of the pair) or a mix
        of static and dynamic fields is rejected — otherwise ``swap_request_body`` would take the
        dynamic branch and fail closed on every request.
        """
        if not channel.credentials.enabled:  # pylint: disable=no-member
            return
        credentials = channel.credential_values
        has_static = bool(credentials.get("soap_security"))
        has_username = bool(credentials.get("soap_username"))
        has_password = bool(credentials.get("soap_password"))
        static_only = has_static and not (has_username or has_password)
        dynamic_only = has_username and has_password and not has_static
        if not (static_only or dynamic_only):
            raise ValueError(
                f"channel {channel.name!r}: SOAP credential swap requires exactly one of "
                "'soap_security' or the complete pair 'soap_username'+'soap_password'"
            )

    def swap_request_body(self, root: etree._Element, context: SwapContext) -> bool:
        credentials = context.channel.credential_values
        if not credentials:
            return False
        target = self._security_target(root, credentials)
        if target is None:
            # No swap target located — e.g. an Amadeus stateful non-start request whose session
            # lives in awsse:Session outside Security. A placeholder UsernameToken must never reach
            # the supplier, so fail closed if one is present anywhere; otherwise this is a no-op.
            if _find_first_by_local(root, _USERNAME_TOKEN) is not None:
                raise CredentialSwapError("SOAP UsernameToken present but no swap target located")
            return False
        if _contains_binary_security_token(target):
            # Session-reuse request: the BinarySecurityToken was already restored to plaintext by
            # request de-anonymization; forward it as-is. A coexisting UsernameToken would be a
            # placeholder we must not leak — fail closed rather than skip.
            if _find_first_by_local(target, _USERNAME_TOKEN) is not None:
                raise CredentialSwapError("SOAP Security carries both a BinarySecurityToken and a UsernameToken")
            return False
        if credentials.get("soap_username"):
            fragment = _dynamic_security_fragment(credentials)
        else:
            fragment = _require_credential(credentials, "soap_security")
        _replace_with_fragment(target, fragment)
        return True

    def swap_response(self, root: etree._Element, context: SwapContext) -> bool:
        if not self.requires_response_keyring(context.channel):
            return False
        if context.keyring is None:
            raise CredentialSwapError("response auth encryption requires keyring")
        changed = False
        for element in root.iter("*"):
            if _local_name(element) not in self.response_auth_local_names or element.text is None:
                continue
            if TOKEN_RE.fullmatch(element.text):
                continue
            element.text = encrypt(element.text, context.keyring)
            changed = True
        return changed

    def _security_target(self, root: etree._Element, credentials: dict[str, str]) -> etree._Element | None:
        """Locate the swappable SOAP security element, or ``None`` when there is nothing to swap.

        An absent ``Security`` element / xpath match returns ``None`` (the swap is a no-op, e.g. a
        session-reuse request). Only a malformed ``soap_security_target_xpath`` expression fails closed.
        """
        target_xpath = credentials.get("soap_security_target_xpath")
        if target_xpath:
            try:
                located_raw: object = root.xpath(target_xpath, namespaces=_namespaces(root))
            except etree.XPathError as exc:
                raise CredentialSwapError("soap_security_target_xpath is invalid") from exc
            if not isinstance(located_raw, list) or not located_raw:
                return None
            target = located_raw[0]
            return target if isinstance(target, etree._Element) else None  # pylint: disable=protected-access
        header = _soap_header(root)
        if header is None:
            return None
        for child in header:
            if isinstance(child.tag, str) and _local_name(child) == _SECURITY:
                return child
        return None


@dataclass(frozen=True, slots=True)
class AmadeusHandler(SoapSecurityHandler):
    """Amadeus SOAP handler."""

    channel_type: ChannelType = ChannelType.AMADEUS
    # SequenceNumber is a non-secret conversation counter the client parses as an int and
    # increments; encrypting it would break session continuity, so only the auth-bearing
    # SessionId/SecurityToken are protected.
    response_auth_local_names: ClassVar[set[str]] = {"SessionId", "SecurityToken"}


@dataclass(frozen=True, slots=True)
class SabreHandler(SoapSecurityHandler):
    """Sabre SOAP handler."""

    channel_type: ChannelType = ChannelType.SABRE
    response_auth_local_names: ClassVar[set[str]] = {"BinarySecurityToken"}


@dataclass(frozen=True, slots=True)
class TravelportHandler(SoapSecurityHandler):
    """Travelport SOAP handler."""

    channel_type: ChannelType = ChannelType.TRAVELPORT
