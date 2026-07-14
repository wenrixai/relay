# Tasks — restore WP_* environment backward compatibility

## 0. Decision gate

- [ ] 0.1 Confirm with the product owner: implement v1 `WP_*` parity, OR explicitly retire the claim.
  If retiring, skip to task 4 (docs/decision) instead.

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/` parity suite: a representative v1 `WP_CHANNELS_*`/`WP_SERVER_*` sample synthesizes the expected channel set (assert channel names/types/hosts/credentials mapping).
- [ ] 1.2 `WP_*`-only startup (no `relay.json`) boots and serves the synthesized channels.
- [ ] 1.3 Precedence test: `relay.json` present alongside `WP_*` resolves per the documented rule.
- [ ] 1.4 Invalid synthesized config → sanitized abort (no credential values).

## 2. Implementation

- [ ] 2.1 Add `config/legacy_env.py`: parse `WP_CHANNELS_*`/`WP_SERVER_*` into `ChannelConfig`/`RelayConfig`.
- [ ] 2.2 Wire it into `config/loader.py` startup with the documented precedence; validate via the same models.

## 3. Docs

- [ ] 3.1 Document `WP_*` as deprecated-but-functional with the mapping and precedence.

## 4. Alternative (if retiring parity)

- [ ] 4.1 Update D17 (add the drop), CLAUDE.md guardrail, and `docs/PROJECT.md` §1.3/§6.2; remove the `loader.py` TODO.

## 5. Verify

- [ ] 5.1 `openspec validate restore-wp-env-backward-compat --strict`.
- [ ] 5.2 `just ci` green.
