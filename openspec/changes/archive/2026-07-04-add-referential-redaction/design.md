## Context

The PII engine (`src/channel_relay/pii/engine.py`) redacts channel responses with rule-driven,
structural edits: `select_rules` matches on channel+operation, `_locate` runs a rule's XPath, and
`_rewrite_node` applies the action to that one node's text/attribute. De-anonymization is separate
and envelope-driven: `deanonymize_request_body` decrypts values that **full-match** `TOKEN_RE`.

Airline channels embed PII inside free text (Amadeus/Sabre `RM`/`OSI`/`SSR` remark lines). Those
values are the same names/passport numbers that structured field rules already know how to find —
but in prose, not in their own node. There is no persistence of PII (guardrail), so "past
extraction" can only mean *earlier in the same redaction pass on the same document*.

Constraints carried from project guidance: structural edits only (no regex/text
find-and-replace on the raw body), fail-closed on any crypto/rule/XML error, XML only via the
hardened `xml_ops` factory, confidentiality-only crypto, no new PII persistence, no retries.

## Goals / Non-Goals

**Goals:**
- A `reference` rule kind that redacts occurrences of already-extracted PII values inside bounded
  free-text nodes, with a reversible `encrypt` action so the channel round-trips to plaintext.
- Two-phase response redaction (collect plaintext → search+rewrite free text) in one pass.
- Embedded `ENC_` token de-anonymization so tokens inside prose survive the return trip.
- Guards (bounded target path, word boundary, min length, case-insensitivity) to contain the
  inherent over-redaction risk of substring matching.

**Non-Goals:**
- Cross-request / cross-document memory of extracted values (would need persistence — forbidden).
- Fuzzy/semantic name matching, transliteration, or NER. Matching is literal on collected values.
- JSONPath free-text targets (deferred with the rest of jsonpath, per existing O6).
- Redacting PII the channel *originates* that no structured rule ever extracted.

## Decisions

### D1: Reference rule references extracted values by `pii_type`, not by rule id
The rule declares `source_pii_types: [person, ...]`. Phase 1 buckets every value a `field` rule
matched by that rule's `pii_type`; phase 2 hunts values in the union of the requested buckets.
- *Why:* loose coupling — remark-scrub rules do not break when a name field rule is renamed, and one
  reference rule covers first+last+middle if all are typed `person`.
- *Alternative (rejected):* explicit `source_rule_ids`. Tighter/more precise but brittle config and
  more churn; can be added later as an optional narrowing without breaking the pii_type model.

### D2: Bounded target path (Model B), not document-wide hunt (Model A)
A reference rule carries `path`/`path_type`/`namespaces` exactly like a field rule; the search runs
**only** inside those located nodes' text. It never walks the whole tree.
- *Why:* blast-radius control. Substring matching against real names ("May", "Will", "Li", "John"
  inside "Johnson") is unsafe document-wide; scoping to vetted remark/OSI nodes is the difference
  between a targeted scrub and shredding coded fields the channel needs.
- *Alternative (rejected):* value-driven doc-wide search. Catches names anywhere but over-redacts
  structured/coded fields; not worth the risk for v1.

### D3: Reversible `encrypt` action; de-anon extended to embedded tokens
Reference rules use the `encrypt` action (same `EncryptAction` model). Because the token is embedded
in prose, `deanonymize_request_body` changes from `TOKEN_RE.fullmatch` to `TOKEN_RE.finditer`,
decrypting each hit in a text/attribute value.
- *Why:* the user's use case is anonymize-out, plaintext-back-to-channel — that is exactly
  `encrypt`. Full-match de-anon would silently ship an `ENC_` token to the channel where a name
  belongs.
- *Token boundary:* base64url alphabet is `[A-Za-z0-9_-]`; the codec's `TOKEN_RE` stops at any char
  outside it (space/punctuation), so `finditer` cleanly bounds each token. Phase 2 guarantees a
  separator survives around each inserted token (it replaces only the matched span, leaving
  surrounding whitespace/text intact), so `A8..` cannot fuse with a following word.
- *Alternative (rejected):* one-way mask/replace for free text. Simpler, no de-anon change, but
  loses round-trip — the channel would receive `*****` instead of the real name.

### D4: Collect plaintext BEFORE phase-1 rewrite
Phase 1 must capture the pre-encryption plaintext (`"John"`), not the post-rewrite token, so phase 2
has literals to search for. Ordering: **collect → rewrite structured nodes → search+rewrite free
text → serialize once.**
- *Why:* if we read node text after `_rewrite_node`, we would search remarks for `ENC_...` which is
  not in the prose. Capturing during `_locate` iteration, before the action, is the only correct
  order.

### D5: Fresh token per occurrence
Each free-text hit is encrypted independently (randomized IV → distinct tokens for the same name).
Both decrypt to the same plaintext.
- *Why:* simplest (reuse `encrypt` as-is) and avoids letting a channel correlate identical tokens.
  Confidentiality-only v1 does not need deterministic tokens.

### D6: Match guards — word boundary + min length + case-insensitive, structural rewrite
Matching finds spans of a collected value inside `node.text` using Python string search under the
guards, then rewrites `node.text` by splicing the encrypted token over each matched span.
- `min_match_len` (default 3) skips ultra-short values that match everywhere.
- `word_boundary` (default true) requires non-alphanumeric neighbours so "John" does not hit
  "Johnson".
- Case-insensitive compare; the original casing of surrounding text is preserved (only the matched
  span is replaced).
- This is still *structural*: it edits the parsed element's `.text`, never the raw body bytes, and
  never uses a rule-supplied regex against the body (the collected value is a fixed literal, escaped
  before any boundary check).

## Risks / Trade-offs

- **Over-redaction of legit prose** ("MAY", "WILL" as names) → guards + bounded target path reduce
  but cannot eliminate it; documented as an authoring caution in `pii-rule-authoring`. Reversible
  encrypt means an over-redacted span still round-trips correctly *if it returns*.
- **Under-redaction** (name spelled differently in prose than in the structured field) → out of
  scope; literal matching only. Called out as a Non-Goal.
- **Token fusing / mangling on return** (client concatenates a token with following text) → D3
  boundary guarantee + a scenario asserting a token adjacent to punctuation still de-anonymizes;
  malformed embedded token fails closed to 502 `pii_deanonymization_failed`.
- **Ordering regressions** in the shared pass → phase split is internal to `redact_response_body`;
  field-only channels behave identically (no reference rules → phase 2 is a no-op).
- **Performance** (search N collected values across M nodes) → bounded by target path; values are
  deduped and length-filtered before search. Still O(N·M) worst case but on small remark sets.

## Migration Plan

Additive. Existing rulesets with only `field` rules validate and behave unchanged (the new
discriminator defaults keep `field` the implied kind). The de-anon change is backward compatible:
full-match tokens are a subset of embedded matches. No `WP_*` change, no key regeneration, no
config migration. Rollback = revert the change; older baked bundles still load.

## Open Questions

- Should `source_rule_ids` narrowing ship in v1 or wait for a real need? (Leaning wait — D1.)
- Do any live channels round-trip remark fields at all? If none do, `encrypt` is effectively
  one-way in practice, but keeping it reversible costs nothing and is safer.
