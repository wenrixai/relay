## Why

Some upstream channels (self-hosted mocks, staging endpoints, or supplier test environments) present
TLS certificates the relay's trust store cannot validate (self-signed, wrong CN, expired). Today there
is no way to reach such a channel through the relay at all — the httpx client always verifies the
upstream server certificate. Operators need an explicit, narrowly-scoped opt-out, without weakening
TLS verification for every other channel sharing the same relay process.

## What Changes

- Add a per-channel `tls.insecure_skip_verify` config flag (default `false`) to `ChannelConfig`. When
  `true`, the relay does not validate the upstream's TLS server certificate for that channel's
  upstream calls only.
- The relay builds a second httpx client with `verify=False`, created only when at least one
  configured channel sets `tls.insecure_skip_verify: true`; all other channels keep using the existing
  verifying client. Selection happens once per request, by channel, before forwarding.
- Startup emits a WARNING log naming every channel with `tls.insecure_skip_verify: true`, since it
  weakens transport security for that upstream. This is an explicit opt-in, so startup does NOT abort
  (unlike credential/PII misconfiguration, which fails closed).
- JSON Schema (`config/json_schema.py` generation) picks up the new field automatically; no hand
  editing.

## Capabilities

### New Capabilities
(none — this extends the existing configuration capability)

### Modified Capabilities
- `relay-configuration`: adds the `tls.insecure_skip_verify` per-channel field, its default, and the
  startup warning requirement, alongside the existing `pii`/`credentials`/`authorization` per-channel
  toggles.

## Impact

- `config/models.py`: new `ChannelTLS` model + `ChannelConfig.tls` field.
- `config/json_schema.py`: no code change; generated schema picks up the new model.
- `main.py`: `build_http_client` gains a `verify` parameter; lifespan conditionally builds a second
  insecure client; route handler selects client per channel; startup warning for insecure channels.
- `proxy/forwarder.py`: no signature change — `forward()` keeps taking a single `client` argument; the
  caller (route handler) picks which client to pass.
- No change to PII crypto, credential swap, or the token format — this only affects transport-level
  TLS verification of the upstream server certificate.
