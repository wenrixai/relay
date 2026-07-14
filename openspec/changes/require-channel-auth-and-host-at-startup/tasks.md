# Tasks — require resolvable upstream and complete swap credentials at startup

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_main_startup.py` (or `test_config.py`): an LA-NDC / Travelport channel with no `host`/`proxy_pass` → startup aborts naming the channel.
- [ ] 1.2 Regression: a channel of the same type WITH `host` or `proxy_pass` boots normally.
- [ ] 1.3 `tests/unit/test_channel_credential_swap.py`: enabled Farelogix missing a required field → startup aborts (not a per-request 502).
- [ ] 1.4 Same for enabled Travelfusion missing a login field, and enabled BA/LA NDC missing the API key.
- [ ] 1.5 Regression: `credentials.enabled=false` on each of those types → no credential requirement, boots.

## 2. Resolvable-upstream validation (#6)

- [ ] 2.1 Add a validator (model_validator on `RelayConfig`/`ChannelConfig`, or a startup check in `main`) that aborts when `proxy_pass` is `None` after `_apply_host_defaults`, naming the channel.

## 3. Credential validation for remaining handlers (#5)

- [ ] 3.1 Implement `validate_credentials` for `TravelfusionHandler` (require `login_id`, `xml_login_id`; validate supplier-parameter shape if present).
- [ ] 3.2 Implement `validate_credentials` for `FarelogixHandler` (require username/password/agent/agent_password/agent_user + subscription key).
- [ ] 3.3 Implement `validate_credentials` for `NdcHeaderHandler` (require the configured API-key credential).
- [ ] 3.4 Remove `NoCredentialValidationMixin` from those handlers (keep it only where a handler genuinely has no required credentials). Ensure errors name the channel, never a value.

## 4. Verify

- [ ] 4.1 Targeted suites green.
- [ ] 4.2 `openspec validate require-channel-auth-and-host-at-startup --strict`.
- [ ] 4.3 `just ci` green.
