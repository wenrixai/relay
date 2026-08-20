## Context

`pii/codec.py` has offered two encryption modes since before v1.0.0: random-IV AES-256-CTR under
`K_enc` (control bit 5 clear) and deterministic AES-256-SIV under `K_siv` (bit 5 set). CTR has been
the default; SIV was opt-in per rule via `"deterministic": true`.

Measured current state on this branch, static master key, `tests/fixtures/amadeus/pnr_retrieve_response.xml`:

| Property | Result |
| --- | --- |
| HKDF derivation of `K_enc`/`K_siv` across reloads | stable, byte-identical |
| Round-trip decrypt under a reloaded keyring | stable (12/12 tokens) |
| Same value repeated within one response | stable (12 tokens, 6 unique — the pass cache) |
| Same payload across two requests | **0 token overlap** |

`rules_fallback.json` (`amadeus+sabre+travelfusion+travelport+farelogix-remarks-2026-08-12`) holds
215 rules: 100 `encrypt`, 110 `replace`, 5 `mask`. **Zero** carry `deterministic: true`. So no
encrypted field is correlatable today, and getting there rule-by-rule means editing 100 rules.

Constraints:
- The `ENC_` wire format does not change. Bit 5 is already specified, already emitted by the encoder,
  and already routed by `decrypt`.
- No request-level retries, no rule polling, no new configuration surface (CLAUDE.md golden rules).
- `decrypt` must stay mode-agnostic so the request path needs no rule knowledge (§8.6).

## Goals / Non-Goals

**Goals:**
- `encrypt` actions produce deterministic, equality-comparable tokens by default.
- `"deterministic": false` per rule remains a working, tested opt-out.
- Zero migration: existing rulesets load unchanged, outstanding random-IV tokens keep decrypting.
- The spec files stop describing random-IV as "the default".

**Non-Goals:**
- Removing the random-IV CTR path. Both modes stay; only the default moves.
- Any new env var, `relay.json` field, or global kill switch. The per-rule flag is the control.
- Editing `rules_fallback.json`. The point of the change is not to need 100 edits.
- Persisting or widening the intra-pass token cache. Stability now comes from the cipher, not state.
- Adding integrity/authentication guarantees as a headline. SIV does authenticate its tag, but the
  v1 threat model still leans on TLS for transport integrity; this change does not restate that.

## Decisions

**Flip the default at the two declaration sites, not at the call sites.**
`codec.encrypt(..., deterministic: bool = True)` and `EncryptAction.deterministic: bool = Field(default=True)`.
`engine._encrypt_cached` already threads `action.deterministic` through and keys the cache on it, so
it needs no logic change — only its comment. Alternative considered: leave the codec default alone
and flip only the pydantic field. Rejected: it leaves `encrypt("x", kr)` — used directly in tests and
reachable by any future caller — silently on the weaker-stability path, so the two layers would
disagree about what "default" means.

**No global config toggle.** A `RELAY_PII_DETERMINISTIC` env var would add a third source of truth
over a property that rule authors already control per field, and a wrong value would silently change
the privacy posture of every channel at once. The per-rule flag is finer-grained and already
validated. Alternative considered and rejected on the "no speculative configurability" rule.

**Keep `K_enc` derived and the CTR path live.** Removing it would break `deterministic: false`,
force a spec removal rather than a modification, and orphan the `K_enc` HKDF label. Cost of keeping
it is one unused-in-practice code path with existing test coverage.

**Deploy ordering is a non-issue, verified rather than assumed.** `git merge-base --is-ancestor` puts
the bit-5 commit (`da2f23c`) before every tag from v1.0.0 through v1.8.8, so no deployed relay treats
bit 5 as a reserved bit. The docstring's warning about relays that predate bit 5 no longer describes
any live version and is removed. Had this not held, the change would have needed a two-phase rollout.

## Risks / Trade-offs

- **Equality of every encrypted field leaks to anyone holding two responses** → This is the accepted
  cost of the request and is now written into the `token-codec` and `pii-rules` specs as a default
  property rather than a per-rule footnote, so rule authors read it before authoring. Mitigation
  available per field: `"deterministic": false`. Follow-up worth considering separately: audit the
  100 encrypt rules and opt out the ones where correlation is most damaging (e.g. document numbers,
  where equality across unrelated PNRs is a stronger signal than for a surname).
- **A static master key now makes tokens stable indefinitely** → previously a leaked key was needed
  to link values; now linking needs no key at all, and the window is the key's whole lifetime. Key
  rotation was removed from the relay (`key-rotation-removed-kms-later`) and is deferred to a KMS
  plugin, so there is no rotation lever to shorten that window today. Called out here rather than
  mitigated.
- **AES-SIV costs two AES passes (S2V then CTR) versus CTR's one** → values are tens of bytes and
  the known hot spot is repeated XML re-parsing, not the cipher. `just perf` guards the envelope.
- **Tests that asserted "default ⇒ different tokens" would now assert the opposite** → they are
  updated to pin `deterministic=False` explicitly where they exercise random-IV behavior, and new
  tests assert the default itself, so neither mode loses coverage.
- **A rule author who wanted random-IV and omits the flag now silently gets correlatable tokens** →
  the spec change makes the default explicit and the generated JSON Schema records `default: true`;
  the failure mode is a weaker privacy property, never a crash or a decrypt failure.

## Migration Plan

None required. Deploy is a normal rolling upgrade:
1. Merge and release. Every relay version in the field already decrypts bit-5 tokens.
2. New responses mint deterministic tokens; in-flight and stored random-IV tokens keep decrypting
   through the same `decrypt` entry point.
3. Rollback is a plain revert. Tokens minted while the new default was live remain decryptable by
   the reverted build — the reverted code still reads bit 5, it just stops setting it.

No key regeneration, no rules-file edit, no ordering constraint between relay and caller deploys.

## Open Questions

- Should any of the 100 existing encrypt rules opt out of the new default? Proposed as a separate
  rules-authoring pass rather than bundled here, so this change stays a one-line default flip and
  the rule-by-rule privacy argument gets its own review.
