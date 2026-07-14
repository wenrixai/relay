# Restore WP_* environment backward compatibility (v1 parity)

## Why

`docs/PROJECT.md` §1.3/§6.2 and CLAUDE.md golden rule #1 make v1 (`WP_*`) backward compatibility a
non-negotiable: on startup the relay reads deprecated `WP_CHANNELS_*` / `WP_SERVER_*` variables and
synthesizes channel entries so existing v1 deployments run on v2 unchanged. `config/loader.py:8` only
carries a comment — *"WP_* legacy synthesis is a later task (T4.3)"* — and no synthesis exists
anywhere in `src/`. Consequently:

- v1 deployments driven purely by `WP_*` env vars cannot run on v2 at all.
- The `docs/PROJECT.md` §13 required "legacy WP_* parity" test suite cannot exist and does not.
- This gap is not listed in D17's deferral set, so it is an undocumented divergence from a stated
  non-negotiable, not an intentional descope.

This change either implements the compat layer or, if v1 parity is being deliberately dropped for v2,
records that as an explicit decision so the guardrail and docs stop asserting a capability that does
not exist.

## What Changes

- On startup, when no JSON config file is present (or as a documented merge/precedence rule), the
  relay SHALL read `WP_CHANNELS_*` / `WP_SERVER_*` variables and synthesize equivalent channel
  configuration, documented as deprecated-but-functional.
- Add a `WP_*` → `relay.json` parity test suite driven by a representative v1 config sample.
- If instead the decision is to drop v1 parity: update D17 (add the deferral/drop), CLAUDE.md, and
  `docs/PROJECT.md` §1.3/§6.2 to remove the compatibility claim, and delete the stale TODO.

## Capabilities

### Modified Capabilities
- `relay-configuration`: `WP_*` legacy variables are synthesized into channel configuration on
  startup (or the compatibility claim is explicitly retired).

## Impact

- `src/channel_relay/config/loader.py` (+ a `legacy_env.py` per the PROJECT.md layout): `WP_*`
  synthesis and precedence.
- `tests/`: `WP_*` parity suite against a v1 sample.
- Docs: mark `WP_*` deprecated-but-functional, or retire the claim.
