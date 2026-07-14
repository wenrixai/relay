"""Pydantic configuration models — the single source of truth (the relay-configuration spec).

Only ``name`` and ``type`` are required on a channel; ``host`` defaults per type and
``proxy_pass`` defaults to ``https://<host>``. The JSON Schema is generated from these
models (``json_schema.py``); it is never hand-maintained.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChannelType(StrEnum):
    """Supported channel types (the relay-configuration spec). Selects parser + swap behaviour."""

    TRAVELFUSION = "travelfusion"
    BA_NDC_DIRECT = "ba-ndc-direct"
    LA_NDC_DIRECT = "la-ndc-direct"
    FARELOGIX_AA = "farelogix-aa"
    FARELOGIX_LH = "farelogix-lh"
    FARELOGIX_UA = "farelogix-ua"
    FARELOGIX_EK = "farelogix-ek"
    AMADEUS = "amadeus"
    SABRE = "sabre"
    TRAVELPORT = "travelport"


# Per-type default host (the relay-configuration spec). ``None`` = per-deployment; host must be supplied.
_DEFAULT_HOSTS: dict[ChannelType, str | None] = {
    ChannelType.TRAVELFUSION: "api.travelfusion.com",
    ChannelType.BA_NDC_DIRECT: "api.ba.com",
    ChannelType.LA_NDC_DIRECT: None,
    ChannelType.FARELOGIX_AA: "aa.farelogix.com",
    ChannelType.FARELOGIX_LH: "lhg.farelogix.com",
    ChannelType.FARELOGIX_UA: "ua.farelogix.com",
    ChannelType.FARELOGIX_EK: "ek.farelogix.com",
    ChannelType.AMADEUS: "nodeD3.production.webservices.amadeus.com",
    ChannelType.SABRE: "webservices.platform.sabre.com",
    ChannelType.TRAVELPORT: None,
}


class Timeouts(BaseModel):
    """Per-channel connect/read timeouts in seconds. No retries on timeout (§10.5)."""

    model_config = ConfigDict(extra="forbid")

    connect: int = Field(default=30, description="Upstream connect timeout, in seconds.")
    read: int = Field(default=120, description="Upstream read timeout, in seconds.")


class ChannelPII(BaseModel):
    """Per-channel PII toggle; redaction/de-anonymization are opt-in (default off)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable PII redaction/de-anonymization for this channel.")
    force_redact: bool = Field(
        default=False,
        description="Replace `encrypt` actions with a fixed REDACTED placeholder instead of "
        "encrypting; no reversible token is produced. For customers who do not want encryption.",
    )


class Credentials(BaseModel):
    """Per-channel credential swap config. Credential values are extra string keys."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False, description="Enable credential swap for this channel.")

    @model_validator(mode="after")
    def _validate_values(self) -> Credentials:
        for key, value in (self.model_extra or {}).items():
            if not isinstance(value, str):
                msg = f"credential {key!r} must be a string"
                raise ValueError(msg)
        return self

    @property
    def values(self) -> dict[str, str]:
        """Channel-specific credential fields, excluding control fields."""
        return {key: value for key, value in (self.model_extra or {}).items() if isinstance(value, str)}


class AllowedOperation(BaseModel):
    """An operation permitted for a channel, with a semver match expression."""

    model_config = ConfigDict(extra="forbid")

    operation: str = Field(description="Operation name as parsed from the request body.")
    version: str = Field(description="Semver match expression the operation's version must satisfy.")


class ExternalAuthorization(BaseModel):
    """Advanced (external) authorization config; later phase (§12.1)."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="External authorization service endpoint.")
    strict: bool = Field(default=False, description="Reject the request if the external check fails or errors.")


class Authorization(BaseModel):
    """Per-channel authorization. Disabled by default; empty ``allowed_operations`` = allow all."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable operation allow-list enforcement.")
    allowed_operations: list[AllowedOperation] = Field(
        default_factory=list, description="Operations allowed for this channel; empty allows all."
    )
    external: ExternalAuthorization | None = Field(default=None, description="Optional external authorization check.")


class ChannelConfig(BaseModel):
    """A single upstream channel. Only ``name`` and ``type`` are required (§5.1)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Unique; used in route /channel/<name>/...")
    type: ChannelType = Field(description="Channel type; selects parser + swap behaviour.")
    host: str | None = Field(default=None, description="Upstream host; sets Host + SNI.")
    proxy_pass: str | None = Field(default=None, description="Full upstream base; overrides host.")
    timeouts: Timeouts = Field(
        default_factory=Timeouts, description="Connect/read timeouts for this channel's upstream."
    )
    credentials: Credentials = Field(
        default_factory=Credentials, description="Credential values used for structural swap into requests."
    )
    pii: ChannelPII = Field(default_factory=ChannelPII)
    authorization: Authorization = Field(
        default_factory=Authorization, description="Allowed operations and external auth checks."
    )

    @field_validator("host")
    @classmethod
    def _validate_host(cls, value: str | None) -> str | None:
        """Fail at load, not at request time: host is a bare hostname (sets Host + SNI)."""
        if value is None:
            return value
        if not value or "://" in value or "/" in value:
            msg = "host must be a bare hostname (no scheme, no path)"
            raise ValueError(msg)
        return value

    @field_validator("proxy_pass")
    @classmethod
    def _validate_proxy_pass(cls, value: str | None) -> str | None:
        """Fail at load, not at request time: proxy_pass is the full upstream base URL."""
        if value is None:
            return value
        if not value.startswith(("http://", "https://")):
            msg = "proxy_pass must be an http:// or https:// URL"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _apply_host_defaults(self) -> ChannelConfig:
        """Fill ``host`` from the per-type default and derive ``proxy_pass``.

        A channel type with no default host must supply ``host`` or ``proxy_pass``: otherwise the
        channel would resolve to no upstream, boot "ready", and return an internal error on every
        request. Fail at load instead (§relay-configuration: startup aborts on invalid config).
        """
        if self.host is None:
            self.host = _DEFAULT_HOSTS.get(self.type)
        if self.proxy_pass is None and self.host is not None:
            self.proxy_pass = f"https://{self.host}"
        if self.proxy_pass is None:
            msg = (
                f"channel {self.name!r} (type {self.type.value!r}) has no resolvable upstream: "
                "set 'host' or 'proxy_pass'"
            )
            raise ValueError(msg)
        return self

    @property
    def credential_values(self) -> dict[str, str]:
        """Enabled channel credential values used by handlers."""
        # pylint: disable=no-member
        if not self.credentials.enabled:
            return {}
        return self.credentials.values

    @property
    def credential_swap_enabled(self) -> bool:
        """True when credential swap is explicitly enabled and values are present."""
        return bool(self.credential_values)

    @property
    def operation_authorization_enabled(self) -> bool:
        """True when operation approval is explicitly enabled and has rules to enforce."""
        # pylint: disable=no-member
        return self.authorization.enabled and bool(self.authorization.allowed_operations)


class RelayConfig(BaseModel):
    """Top-level relay configuration: the set of configured channels."""

    model_config = ConfigDict(extra="forbid")

    channels: list[ChannelConfig] = Field(default_factory=list, description="All configured upstream channels.")

    @model_validator(mode="after")
    def _validate_unique_names(self) -> RelayConfig:
        """Duplicate names would silently shadow a channel's routing and credentials."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for channel in self.channels:
            if channel.name in seen:
                duplicates.add(channel.name)
            seen.add(channel.name)
        if duplicates:
            msg = f"duplicate channel name(s): {', '.join(sorted(duplicates))}"
            raise ValueError(msg)
        return self
