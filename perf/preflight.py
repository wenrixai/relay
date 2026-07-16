"""Prove that each measured perf scenario reaches its intended relay pipeline stage."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx

from channel_relay.pii.codec import TOKEN_RE, encrypt
from channel_relay.pii.crypto import Keyring
from channel_relay.pii.xml_ops import parse_bytes

_ROUNDTRIP_PLAINTEXT = "PERF_ROUNDTRIP_PLAINTEXT"


def _post(relay_url: str, channel: str, body: str) -> httpx.Response:
    response = httpx.post(
        f"{relay_url.rstrip('/')}/channel/{channel}/",
        content=body.encode(),
        headers={"content-type": "application/xml"},
        timeout=10,
    )
    response.raise_for_status()
    return response


def _assert_redacted(response: httpx.Response) -> None:
    root = parse_bytes(response.content)
    name_parts = root.xpath("//*[local-name()='NamePart']/text()")
    if len(name_parts) != 1 or TOKEN_RE.fullmatch(str(name_parts[0])) is None:
        raise RuntimeError("perf preflight: response redaction did not produce an ENC_ token")
    if _ROUNDTRIP_PLAINTEXT.encode() in response.content or b"PERF TRAVELLER" in response.content:
        raise RuntimeError("perf preflight: plaintext survived response redaction")


def run_preflight(relay_url: str, keyring: Keyring) -> str:
    passthrough = _post(relay_url, "passthrough", "<Envelope><PerfMarker>PASSTHROUGH</PerfMarker></Envelope>")
    if b"PERF TRAVELLER" not in passthrough.content:
        raise RuntimeError("perf preflight: pass-through response was unexpectedly inspected")

    swap = _post(
        relay_url,
        "swap",
        "<CommandList><GeneralInfoItemList/><StartRouting><LoginId>caller-login</LoginId>"
        "<XmlLoginId>caller-xml</XmlLoginId><CustomSupplierParameterList/></StartRouting></CommandList>",
    )
    if swap.headers.get("x-perf-mock-saw-swapped-credentials") != "true":
        raise RuntimeError("perf preflight: Travelfusion credential swap did not execute")

    _assert_redacted(_post(relay_url, "redact", "<CommandList><GetBookingDetails/></CommandList>"))

    token = encrypt(_ROUNDTRIP_PLAINTEXT, keyring)
    roundtrip = _post(
        relay_url,
        "roundtrip",
        f"<CommandList><GetBookingDetails><PerfRoundtrip>{token}</PerfRoundtrip></GetBookingDetails></CommandList>",
    )
    if roundtrip.headers.get("x-perf-mock-saw-roundtrip-plaintext") != "true":
        raise RuntimeError("perf preflight: request de-anonymization did not execute")
    _assert_redacted(roundtrip)
    return token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--relay-url", default="http://127.0.0.1:8080")
    parser.add_argument("--token-output", type=Path, required=True)
    args = parser.parse_args()

    keyring_source = os.environ.get("RELAY_PII_KEYRING")
    if keyring_source is None:
        raise RuntimeError("RELAY_PII_KEYRING must be set for the perf preflight")
    token = run_preflight(args.relay_url, Keyring.from_json(keyring_source))
    args.token_output.write_text(token, encoding="utf-8")


if __name__ == "__main__":
    main()
