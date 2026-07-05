"""Channel handler contracts for operation parsing and credential swap (Slice 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lxml import etree

from channel_relay.config.models import ChannelConfig, ChannelType
from channel_relay.pii.crypto import Keyring


class CredentialSwapError(ValueError):
    """Configured credential swap could not be completed; fail closed with 502."""


@dataclass(slots=True)
class SwapContext:
    """Mutable per-request/per-response state passed to a channel handler."""

    channel: ChannelConfig
    headers: dict[str, str]
    keyring: Keyring | None


class ChannelHandler(Protocol):
    """Per-channel parser and structural credential-swap hooks."""

    @property
    def channel_type(self) -> ChannelType:
        """The channel type handled by this implementation."""

    def parse_operation(self, root: etree._Element) -> str:
        """Return the body-derived operation name."""

    def swap_request_headers(self, context: SwapContext) -> None:
        """Inject outbound credential headers. Needs no body; runs for every credentialed channel."""

    def swap_request_body(self, root: etree._Element, context: SwapContext) -> bool:
        """Mutate request XML. Return true when the body changed. Runs only when body inspection is required."""

    def swap_response(self, root: etree._Element, context: SwapContext) -> bool:
        """Mutate response XML. Return true when the XML body changed."""

    def requires_body_inspection(self, channel: ChannelConfig) -> bool:
        """Whether this channel's configured credentials require XML body parsing."""

    def requires_response_keyring(self, channel: ChannelConfig) -> bool:
        """Whether configured response processing requires a PII keyring."""
