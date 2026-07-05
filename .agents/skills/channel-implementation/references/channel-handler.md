# Channel Handler, Config, and Forwarder Wiring

## Purpose

Everything code-side a new channel needs: the type enum, config defaults, the handler
implementing credential swap, registry wiring, and where each hook fires in the forwarder
pipeline. Follow the existing handlers as templates — every swap style already has one.

## 1. Config (`src/channel_relay/config/models.py`)

- Add a member to `ChannelType` (kebab-case value, e.g. `KIWI = "kiwi"`). The type selects the
  parser + swap behavior; the route name (`/channel/<name>/...`) is the config `name`, which is
  independent.
- Add the entry to `_DEFAULT_HOSTS` (a stable public host, or `None` when the host is
  per-deployment and must be supplied in config).
- `ChannelConfig.credentials` is a flat `dict[str, str]` from mounted secrets — define the keys
  your handler needs and document them in the model docstrings (the config reference doc is
  generated from the models). Missing-credential errors must name the key
  (use `_require_credential`).
- Per-channel PII is opt-in via `pii.enabled` (`ChannelPII`); redaction never runs for channels
  that don't enable it.
- The config JSON Schema is generated from these models (`config/json_schema.py`) — never edit
  a schema file by hand.

## 2. Handler (`src/channel_relay/channels/handlers.py`)

Implement the `ChannelHandler` protocol (`src/channel_relay/channels/base.py`):

| Hook | When it runs | Notes |
|---|---|---|
| `parse_operation(root)` | every inspected body | body-derived only; SOAP channels reuse `_soap_operation` |
| `swap_request_headers(context)` | every credentialed request, body never parsed | use `_set_header` — it drops client-sent case variants so no duplicate header reaches the supplier |
| `swap_request_body(root, context)` | only when `requires_body_inspection` is true | structural lxml mutation; return `True` iff changed |
| `swap_response(root, context)` | XML responses of credentialed channels | strip or encrypt supplier-issued secrets before PII redaction |
| `requires_body_inspection(channel)` | routing decision | also gates the request body-size cap — header-only channels must return `False` so oversize/malformed bodies pass through untouched |
| `requires_response_keyring(channel)` | startup + response path | return `True` only if `swap_response` encrypts (needs the PII keyring) |

Compose with the no-op mixins instead of writing empty methods: `NoHeaderSwapMixin`,
`NoBodySwapMixin`, `NoopResponseMixin`. Handlers are frozen slotted dataclasses.

Pick the closest existing style:

- **Header-only key** → `NdcHeaderHandler` (parameterized, no new class needed).
- **XML element text swap** → `TravelfusionHandler`.
- **XML attribute swap + subscription header** → `FarelogixHandler`.
- **SOAP `Security` header replacement** → subclass `SoapSecurityHandler`; set
  `response_auth_local_names` to the local names of supplier-issued session secrets in
  responses (e.g. Sabre `{"BinarySecurityToken"}`, Amadeus
  `{"SessionId", "SequenceNumber", "SecurityToken"}`). Those values are replaced with `ENC_`
  tokens so the client can echo them back on the next request, where generic
  de-anonymization restores them before the security header is swapped.

Failure contract: raise `CredentialSwapError` when a configured swap target is missing or
malformed. The forwarder maps it to HTTP 502 `credential_swap_failed` without forwarding —
never forward a request whose credentials were only partially swapped.

## 3. Registry (`src/channel_relay/channels/__init__.py`)

Add one `_HANDLERS[ChannelType.X] = XHandler()` entry. `get_handler` raises `KeyError` on an
unregistered type, so a forgotten entry fails loudly on first request — the registry unit
tests should cover the new type anyway.

## 4. Forwarder pipeline order (`src/channel_relay/proxy/forwarder.py`)

Fixed order — tests must assert it, handlers must not assume otherwise:

```
request:  header hygiene → swap_request_headers (always)
          → [if PII enabled or body inspection required: decode gzip once, parse]
          → deanonymize ENC_ tokens (PII) → swap_request_body → re-encode gzip once
response: clean hop-by-hop headers → swap_response (credential cleanup)
          → PII redaction (rules) → return
```

Why the order matters: de-anonymization must precede the body swap so restored secrets land
inside structures the swap replaces; response credential cleanup must precede redaction so
supplier session secrets become `ENC_` tokens even on operations with no PII rules.

## 5. Checklist for a new channel

- [ ] `ChannelType` member + `_DEFAULT_HOSTS` entry (+ credential-key docs on the handler)
- [ ] Handler (or parameterized reuse) with the correct mixins
- [ ] Registry entry
- [ ] Unit tests in `tests/unit/test_channel_credential_swap.py` (operation parsing, each swap
      hook, missing-credential failure)
- [ ] Forwarder integration test in `tests/integration/test_credential_swap_forwarder.py`
      (swap before upstream, fail-closed 502, gzip round-trip if body-inspecting)
