"""Tests for pydantic config models, JSON Schema generation, and the loader (T1.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from channel_relay.config.json_schema import generate_json_schema
from channel_relay.config.loader import ConfigValidationError, load_config
from channel_relay.config.models import AllowedOperation, Authorization, ChannelConfig, ChannelType, RelayConfig


def test_minimal_channel_applies_type_host_default() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    assert channel.host == "api.travelfusion.com"
    assert channel.proxy_pass == "https://api.travelfusion.com"


def test_channel_family_collapses_farelogix_variants() -> None:
    for variant in (
        ChannelType.FARELOGIX_AA,
        ChannelType.FARELOGIX_LH,
        ChannelType.FARELOGIX_UA,
        ChannelType.FARELOGIX_EK,
    ):
        assert variant.family == "farelogix"
    # Every non-farelogix type is its own family (the alias is a no-op for them).
    assert ChannelType.AMADEUS.family == "amadeus"
    assert ChannelType.SABRE.family == "sabre"


def test_explicit_host_overrides_default() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION, host="example.test")
    assert channel.host == "example.test"
    assert channel.proxy_pass == "https://example.test"


def test_explicit_proxy_pass_wins() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        proxy_pass="https://override.test/base",
    )
    assert channel.proxy_pass == "https://override.test/base"


def test_per_deployment_type_has_no_host_default() -> None:
    channel = ChannelConfig(name="tp", type=ChannelType.TRAVELPORT)
    assert channel.host is None
    assert channel.proxy_pass is None


def test_timeout_defaults() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    assert channel.timeouts.connect == 30
    assert channel.timeouts.read == 120


def test_pii_off_by_default() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    assert channel.pii.enabled is False


def test_pii_force_redact_off_by_default() -> None:
    channel = ChannelConfig(name="tf", type=ChannelType.TRAVELFUSION)
    assert channel.pii.force_redact is False


def test_credentials_are_disabled_by_default_even_when_values_exist() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"login_id": "relay-login", "xml_login_id": "relay-xml"},
    )
    assert channel.credentials.enabled is False
    assert channel.credentials.values == {"login_id": "relay-login", "xml_login_id": "relay-xml"}
    assert channel.credential_values == {}
    assert channel.credential_swap_enabled is False


def test_credentials_must_be_explicitly_enabled() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        credentials={"enabled": True, "login_id": "relay-login", "xml_login_id": "relay-xml"},
    )
    assert channel.credentials.enabled is True
    assert channel.credential_values == {"login_id": "relay-login", "xml_login_id": "relay-xml"}
    assert channel.credential_swap_enabled is True


def test_credential_values_must_be_strings() -> None:
    with pytest.raises(ValidationError):
        ChannelConfig(
            name="tf",
            type=ChannelType.TRAVELFUSION,
            credentials={"enabled": True, "login_id": 123},
        )


def test_operation_authorization_is_disabled_by_default_even_with_rules() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        authorization=Authorization(allowed_operations=[AllowedOperation(operation="Fare_GetFareRules", version="*")]),
    )
    assert channel.authorization.enabled is False
    assert channel.operation_authorization_enabled is False


def test_operation_authorization_must_be_explicitly_enabled() -> None:
    channel = ChannelConfig(
        name="tf",
        type=ChannelType.TRAVELFUSION,
        authorization=Authorization(
            enabled=True,
            allowed_operations=[AllowedOperation(operation="Fare_GetFareRules", version="*")],
        ),
    )
    assert channel.operation_authorization_enabled is True


def test_channel_tls_block_rejected() -> None:
    # TLS verification is a process-wide setting (RELAY_UPSTREAM_TLS_VERIFY); a channel
    # document must not be able to weaken transport security.
    with pytest.raises(ValidationError):
        ChannelConfig(
            name="tf",
            type=ChannelType.TRAVELFUSION,
            tls={"insecure_skip_verify": True},  # type: ignore[call-arg]
        )


def test_unknown_channel_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ChannelConfig(name="x", type="not-a-channel")  # type: ignore[arg-type]


def test_missing_required_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ChannelConfig()  # type: ignore[call-arg]


def test_generated_schema_marks_name_and_type_required() -> None:
    schema = generate_json_schema()
    # RelayConfig -> channels -> items -> ChannelConfig definition
    defs = schema["$defs"]
    channel_schema = defs["ChannelConfig"]
    assert set(channel_schema["required"]) >= {"name", "type"}


def test_generated_schema_has_no_channel_tls_definition() -> None:
    schema = generate_json_schema()
    assert "ChannelTLS" not in schema["$defs"]
    assert "tls" not in schema["$defs"]["ChannelConfig"]["properties"]


def test_loader_reads_valid_config(tmp_path: Path) -> None:
    cfg = {"channels": [{"name": "tf", "type": "travelfusion"}]}
    path = tmp_path / "relay.json"
    path.write_text(json.dumps(cfg))
    loaded = load_config(path)
    assert isinstance(loaded, RelayConfig)
    assert loaded.channels[0].name == "tf"
    assert loaded.channels[0].host == "api.travelfusion.com"


def test_loader_aborts_on_invalid_config(tmp_path: Path) -> None:
    path = tmp_path / "relay.json"
    path.write_text(json.dumps({"channels": [{"name": "x", "type": "bogus"}]}))
    with pytest.raises(ConfigValidationError):
        load_config(path)


def test_loader_error_never_contains_credential_values(tmp_path: Path) -> None:
    """A failing credentials block must never leak its values into the raised error."""
    cfg = {
        "channels": [
            {
                "name": "tp",
                "type": "travelport",
                "credentials": {"enabled": True, "password": "SUPERSECRET", "login_id": 12345},
            }
        ]
    }
    path = tmp_path / "relay.json"
    path.write_text(json.dumps(cfg))
    with pytest.raises(ConfigValidationError) as excinfo:
        load_config(path)
    rendered = f"{excinfo.value!s} {excinfo.value!r}"
    assert "SUPERSECRET" not in rendered
    assert "12345" not in rendered
    assert "channels.0.credentials" in str(excinfo.value)


def test_loader_error_has_no_cause_chain(tmp_path: Path) -> None:
    """The original ValidationError (which embeds input values) must not chain through."""
    path = tmp_path / "relay.json"
    path.write_text(json.dumps({"channels": [{"name": "x", "type": "bogus"}]}))
    with pytest.raises(ConfigValidationError) as excinfo:
        load_config(path)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


def test_loader_aborts_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist.json")


def test_empty_channels_is_valid() -> None:
    assert RelayConfig().channels == []


def test_duplicate_channel_names_rejected() -> None:
    with pytest.raises(ValidationError, match="tf"):
        RelayConfig.model_validate(
            {
                "channels": [
                    {"name": "tf", "type": "travelfusion"},
                    {"name": "tf", "type": "sabre"},
                ]
            }
        )


def test_distinct_channel_names_accepted() -> None:
    config = RelayConfig.model_validate(
        {
            "channels": [
                {"name": "tf", "type": "travelfusion"},
                {"name": "sabre", "type": "sabre"},
            ]
        }
    )
    assert len(config.channels) == 2


def test_proxy_pass_requires_http_scheme() -> None:
    with pytest.raises(ValidationError):
        ChannelConfig(name="x", type=ChannelType.TRAVELPORT, proxy_pass="webservices.example.com")
    with pytest.raises(ValidationError):
        ChannelConfig(name="x", type=ChannelType.TRAVELPORT, proxy_pass="ftp://example.com")
    channel = ChannelConfig(name="x", type=ChannelType.TRAVELPORT, proxy_pass="http://mock-channel:9000")
    assert channel.proxy_pass == "http://mock-channel:9000"


def test_host_rejects_scheme_path_and_empty() -> None:
    with pytest.raises(ValidationError):
        ChannelConfig(name="x", type=ChannelType.TRAVELPORT, host="https://example.com")
    with pytest.raises(ValidationError):
        ChannelConfig(name="x", type=ChannelType.TRAVELPORT, host="example.com/base")
    with pytest.raises(ValidationError):
        ChannelConfig(name="x", type=ChannelType.TRAVELPORT, host="")
    channel = ChannelConfig(name="x", type=ChannelType.TRAVELPORT, host="example.com")
    assert channel.host == "example.com"
