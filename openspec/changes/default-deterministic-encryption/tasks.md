## 1. Failing tests first (TDD)

- [x] 1.1 In `tests/unit/test_pii_codec.py`, add a test asserting `encrypt(pt, keyring)` with no mode
      argument sets control bit 5 and yields byte-identical tokens across repeated calls.
- [x] 1.2 In `tests/unit/test_pii_codec.py`, retarget the existing random-IV tests
      (`test_encrypt_same_plaintext_differs`-style, `test_deterministic_flag_encoded_in_control`) to
      pass `deterministic=False` explicitly, so both modes keep coverage.
- [x] 1.3 In `tests/unit/test_pii_rules.py`, add a test that an encrypt rule with no `deterministic`
      key loads with `action.deterministic is True`, and one that `deterministic: false` loads as
      `False`.
- [x] 1.4 In `tests/unit/test_pii_engine.py`, add a cross-pass stability test for an encrypt rule that
      omits the flag (two passes → one token), and pin `test_no_cross_pass_reuse_in_default_mode` to a
      `deterministic=False` rule, renaming it to say random-IV.
- [x] 1.5 Confirm the new tests fail and the retargeted ones pass, for the right reasons.

## 2. Implementation

- [x] 2.1 `src/channel_relay/pii/codec.py`: flip `encrypt(..., deterministic: bool = False)` to
      `= True`.
- [x] 2.2 `src/channel_relay/pii/rules.py`: flip `EncryptAction.deterministic` to `default=True` and
      rewrite its `description` to describe the flag as an opt-*out*.
- [x] 2.3 Verify `engine._encrypt_cached` and `_apply_action` need no logic change (they already
      thread and key on `action.deterministic`); update only the comment at `engine.py:44`.

## 3. Docs and generated artifacts

- [x] 3.1 Rewrite the `codec.py` module docstring: deterministic is the default path, random-IV is the
      opt-out, and drop the now-dead "relays that predate bit 5" deploy-order warning (verified
      shipped before v1.0.0).
- [x] 3.2 `docs/PROJECT.md` §8.4 (~line 217): invert the `deterministic` guidance, state the
      default-equality disclosure, and document `deterministic: false` as the opt-out.
- [x] 3.3 Confirm the generated rules JSON Schema records `default: true` for the encrypt action's
      `deterministic` property. No file to regenerate — `rules.generate_rules_json_schema()` produces
      it at runtime and there is no committed `schema.json`; locked by a new test instead.
- [x] 3.4 Corrected every doc that named random-IV the default: `CLAUDE.md` (Security constraints),
      `SECURITY.md` (Controls + out-of-scope), `README.md`, `docs/PROJECT.md` (§8.1, §8.4, §8.5/8.6,
      tech table, locked decisions D1/D2), `docs/SECURITY_POSTURE.md` (§2 out-of-scope, §3.1, §3.2,
      §13). Added the equality disclosure as an explicit out-of-scope item in both security docs.

## 4. Verification

- [x] 4.1 `just test` — full suite green, no slow-test gate violations.
- [x] 4.2 `just cov` — coverage stays at or above the 85% gate.
- [x] 4.3 `just lint`, `just types`, `just pylint`, `just fmt-check` all green.
- [x] 4.4 Re-run the empirical stability check from the investigation: two redaction passes over
      `tests/fixtures/amadeus/pnr_retrieve_response.xml` now produce byte-identical output, and every
      token still round-trips through `deanonymize_request_body` under a freshly loaded keyring.
- [x] 4.5 Confirm a random-IV token minted before the flip still decrypts under the new build
      (the committed historic-token fixture in `test_pii_codec.py` round-trips unchanged).

## 6. Spec sync

- [x] 6.1 Applied the three delta specs into `openspec/specs/{token-codec,pii-rules,redaction-engine}`
      so the merged tree has code and specs agreeing; `openspec validate --specs` green (20/20).
      The change directory stays unarchived, matching the convention of the other landed changes.

## 5. Ship

- [ ] 5.1 Branch, Conventional Commit (`feat(pii)!:` — behavioral breaking change), push.
- [ ] 5.2 Open the PR with the privacy trade-off stated in the body, not just in the spec delta.
