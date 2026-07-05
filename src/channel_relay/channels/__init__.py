"""Channel handler registry."""

from __future__ import annotations

from channel_relay.channels.base import ChannelHandler
from channel_relay.channels.handlers import (
    AmadeusHandler,
    FarelogixHandler,
    NdcHeaderHandler,
    SabreHandler,
    TravelfusionHandler,
    TravelportHandler,
)
from channel_relay.config.models import ChannelConfig, ChannelType

_HANDLERS: dict[ChannelType, ChannelHandler] = {
    ChannelType.TRAVELFUSION: TravelfusionHandler(),
    ChannelType.BA_NDC_DIRECT: NdcHeaderHandler(
        channel_type=ChannelType.BA_NDC_DIRECT,
        credential_key="client_key",
        header_name="Client-Key",
    ),
    ChannelType.LA_NDC_DIRECT: NdcHeaderHandler(
        channel_type=ChannelType.LA_NDC_DIRECT,
        credential_key="api_key",
        header_name="API-Key",
    ),
    ChannelType.FARELOGIX_AA: FarelogixHandler(ChannelType.FARELOGIX_AA),
    ChannelType.FARELOGIX_LH: FarelogixHandler(ChannelType.FARELOGIX_LH),
    ChannelType.FARELOGIX_UA: FarelogixHandler(ChannelType.FARELOGIX_UA),
    ChannelType.FARELOGIX_EK: FarelogixHandler(ChannelType.FARELOGIX_EK),
    ChannelType.AMADEUS: AmadeusHandler(),
    ChannelType.SABRE: SabreHandler(),
    ChannelType.TRAVELPORT: TravelportHandler(),
}


def get_handler(channel_type: ChannelType) -> ChannelHandler:
    """Return the registered handler for ``channel_type``."""
    return _HANDLERS[channel_type]


def credentials_require_body_inspection(channel: ChannelConfig) -> bool:
    """Whether configured channel credentials require request XML inspection."""
    return get_handler(channel.type).requires_body_inspection(channel)


def credentials_require_response_keyring(channel: ChannelConfig) -> bool:
    """Whether configured channel credentials require a response auth keyring."""
    return get_handler(channel.type).requires_response_keyring(channel)
