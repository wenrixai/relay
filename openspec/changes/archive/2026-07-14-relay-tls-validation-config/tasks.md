## 1. Config model

- [x] 1.1 Write failing unit test: `ChannelConfig` without a `tls` block defaults
      `tls.insecure_skip_verify` to `False`.
- [x] 1.2 Write failing unit test: `ChannelConfig` with `tls.insecure_skip_verify: true` validates
      and the field reads back `True`; `extra="forbid"` rejects unknown keys under `tls`.
- [x] 1.3 Add `ChannelTLS` model (`insecure_skip_verify: bool = False`, `extra="forbid"`) to
      `config/models.py`.
- [x] 1.4 Add `tls: ChannelTLS = Field(default_factory=ChannelTLS)` to `ChannelConfig`.
- [x] 1.5 Regenerate/verify the generated JSON Schema picks up the new field (no hand-editing
      `json_schema.py`); update any committed schema fixture/golden file.
- [x] 1.6 Run tests; confirm green.

## 2. HTTP client selection

- [x] 2.1 Write failing unit test: `build_http_client(settings, verify=False)` returns a client
      whose transport does not verify certs (assert on the constructed client/transport config,
      not a live TLS handshake).
- [x] 2.2 Add a `verify: bool = True` parameter to `build_http_client` in `main.py`, passed through
      to `httpx.AsyncClient`/`httpx.AsyncHTTPTransport`.
- [x] 2.3 Write failing integration test: with one channel `tls.insecure_skip_verify: true` and one
      channel default, `app.state.insecure_client` is created and `app.state.client` still verifies;
      with no insecure channels configured, `app.state.insecure_client` is `None`.
- [x] 2.4 In `lifespan()`, after loading config, compute whether any channel has
      `tls.insecure_skip_verify` true; conditionally build `application.state.insecure_client` via
      `build_http_client(settings, verify=False)`, mirroring the existing `owns_client` guard so it's
      only closed if this process created it.
- [x] 2.5 Initialize `application.state.insecure_client = None` alongside the existing
      `application.state.client` assignment.

## 3. Route wiring

- [x] 3.1 Write failing integration test: a request to a channel with
      `tls.insecure_skip_verify: true` is forwarded using the insecure client (mock/spy on which
      client instance received the call); a request to any other channel uses the verifying client.
- [x] 3.2 In the `relay()` route handler, select
      `insecure_client if channel.tls.insecure_skip_verify else client` before calling `forward()`;
      `forward()`'s signature and body stay unchanged.
- [x] 3.3 Run tests; confirm green.

## 4. Startup diagnostics

- [x] 4.1 Write failing unit test: startup logs one WARNING per channel with
      `tls.insecure_skip_verify: true`, naming the channel and stating TLS verification is disabled;
      no channels configured this way → no such warning; startup does not abort either way.
- [x] 4.2 Extend `warn_unenforced_config` (or add a sibling function called alongside it) in
      `main.py` to emit the WARNING for each insecure-TLS channel.
- [x] 4.3 Run tests; confirm green.

## 5. Docs and spec sync

- [x] 5.1 Update `docs/PROJECT.md` where per-channel config toggles are enumerated, if applicable.
- [x] 5.2 Run `just lint`, `just types`, `just pylint`, `just cov` locally.
- [ ] 5.3 Run `openspec archive relay-tls-validation-config` (or the `opsx:archive` skill) once
      merged, to sync the `relay-configuration` spec delta into `openspec/specs/`.
