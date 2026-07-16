"""Fast contracts for the load/performance harness."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from channel_relay.channels import get_handler
from channel_relay.config.models import ChannelType, RelayConfig
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.engine import redact_response_body
from channel_relay.pii.rules_loader import load_baked_rules

REPO_ROOT = Path(__file__).resolve().parents[2]
PERF_CONFIG = REPO_ROOT / "perf" / "relay.perf.json"
PERF_SCRIPT = REPO_ROOT / "perf" / "relay-load.js"
PERF_RESPONSE = REPO_ROOT / "perf" / "mock-response.xml"
PERF_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "perf.yml"


def test_perf_channels_enable_the_stages_they_measure() -> None:
    config = RelayConfig.model_validate(json.loads(PERF_CONFIG.read_text(encoding="utf-8")))
    channels = {channel.name: channel for channel in config.channels}

    assert channels["passthrough"].credential_swap_enabled is False
    assert channels["passthrough"].pii.enabled is False
    assert channels["swap"].type is ChannelType.TRAVELFUSION
    assert channels["swap"].credential_swap_enabled is True
    assert channels["redact"].type is ChannelType.TRAVELFUSION
    assert channels["redact"].pii.enabled is True
    assert channels["roundtrip"].type is ChannelType.TRAVELFUSION
    assert channels["roundtrip"].pii.enabled is True


def test_perf_mock_response_exercises_baked_redaction_rules() -> None:
    keyring = Keyring.from_json("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    ruleset = load_baked_rules()

    redacted, counts = redact_response_body(
        PERF_RESPONSE.read_bytes(),
        channel="travelfusion",
        ruleset=ruleset,
        keyring=keyring,
        operation_parser=get_handler(ChannelType.TRAVELFUSION).parse_operation,
    )

    assert counts["person"] >= 1
    assert b"PERF TRAVELLER" not in redacted
    assert b"ENC_" in redacted


def test_k6_payloads_are_stage_specific_and_require_a_generated_token() -> None:
    script = PERF_SCRIPT.read_text(encoding="utf-8")

    assert "<StartRouting>" in script
    assert "<LoginId>caller-login</LoginId>" in script
    assert "<XmlLoginId>caller-xml</XmlLoginId>" in script
    assert "ROUNDTRIP_TOKEN" in script
    assert "ENC_AAAAAAAAA" not in script
    assert "SUMMARY_PATH" in script


def test_perf_workflow_runs_the_full_payload_matrix_with_unique_artifacts() -> None:
    workflow = yaml.safe_load(PERF_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["k6"]

    assert job["strategy"]["matrix"]["payload_size"] == [2048, 32768, 262144]
    run_step = next(step for step in job["steps"] if step.get("name") == "Run k6")
    upload_step = next(step for step in job["steps"] if step.get("name") == "Upload summary")
    assert "perf/preflight.py" in str(job["steps"])
    assert "matrix.payload_size" in run_step["run"]
    assert "matrix.payload_size" in upload_step["with"]["name"]
    assert "matrix.payload_size" in upload_step["with"]["path"]
