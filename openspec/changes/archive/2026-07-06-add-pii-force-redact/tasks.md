## 1. Config

- [x] 1.1 Add `ChannelPII.force_redact: bool` (default `false`) to `src/channel_relay/config/models.py`
- [x] 1.2 `tests/unit/test_config.py`: default-false test for `force_redact`

## 2. Engine — field rules

- [x] 2.1 `tests/unit/test_pii_engine.py`: failing test — an `encrypt`-method field rule with
      `force_redact=True` yields literal `"REDACTED"` (not `ENC_...`), with `keyring=None`
- [x] 2.2 `src/channel_relay/pii/engine.py`: thread `force_redact: bool` through `_apply_action`,
      `_apply_extracted_actions`, `_rewrite_value`, `_rewrite_node`, `_redact_field_rule`; make
      `keyring: Keyring | None` on these; `_apply_action`'s `EncryptAction` case returns
      `"REDACTED"` when `force_redact`, else `encrypt(value, keyring)`
- [x] 2.3 Confirm existing encrypt-path tests still pass unchanged with default `force_redact=False`

## 3. Engine — reference rules

- [x] 3.1 `tests/unit/test_pii_engine.py`: failing test — a reference rule with `force_redact=True`
      substitutes `"REDACTED"` for matched free-text occurrences, with `keyring=None`
- [x] 3.2 `src/channel_relay/pii/engine.py`: thread `force_redact` into `_redact_reference_rule`;
      `keyring: Keyring | None`; substitute pattern replacement with a `"REDACTED"` literal when
      `force_redact`, else the existing `encrypt(...)` call
- [x] 3.3 `redact_response_body(...)`: add `force_redact: bool = False` param, `keyring: Keyring |
      None`; pass through to both the field-rule and reference-rule loops

## 4. Forwarder wiring

- [x] 4.1 `src/channel_relay/proxy/forwarder.py`: relax the response-side PII gate to
      `channel.pii.enabled and rules is not None and content and response_kind is ContentKind.XML
      and (keyring is not None or channel.pii.force_redact)`
- [x] 4.2 Pass `force_redact=channel.pii.force_redact` into the response PII stage's call to
      `redact_response_body(...)`
- [x] 4.3 Forwarder/integration test: a channel with `pii.enabled=True, pii.force_redact=True` and
      no keyring configured — response is redacted with `"REDACTED"`, no 500/502

## 5. Keyring requirement

- [x] 5.1 `src/channel_relay/main.py`: narrow `build_keyring`'s `keyring_required` predicate to
      `(channel.pii.enabled and not channel.pii.force_redact) or
      credentials_require_response_keyring(channel)`
- [x] 5.2 Test: a config with only a force_redact channel does NOT raise `RuntimeError` for a
      missing keyring at startup
- [x] 5.3 Confirm `pii_required` (rules-loading gate) is unchanged — still keyed on `pii.enabled`
      alone, since rules are needed regardless of the action taken

## 6. Verification

- [x] 6.1 `just test-fast` green
- [x] 6.2 `just ci` green (ruff, mypy, pylint, pytest)
- [x] 6.3 Focused integration check: request through a `pii.force_redact: true` channel with no
      `PII_KEYRING` set — response contains `"REDACTED"` instead of `ENC_...` tokens, no 500/502
      (covered end-to-end by `test_force_redact_channel_needs_no_keyring` in
      `tests/integration/test_pii_roundtrip.py`, which exercises this exact scenario through the
      real FastAPI app)
