## Context

The relay redacts Sabre PII by rewriting selected XML nodes per the baked ruleset
(`rules_fallback.json`). The engine supports four actions — `encrypt`, `mask`, `replace`, `remove`
(`src/channel_relay/pii/rules.py:51-89`; dispatch in `engine.py:_apply_action`). Today the Sabre
DOCS `DateOfBirth` and `Gender` rules and the `PaymentCard` expiry rule use `mask` with the default
mask char `*`. `mask` output is `value[:keep_prefix] + mask_char * (len - keep_prefix)`, so a DOB
`1994-07-01` becomes `**********`.

The Wenrix Sabre caller parses these as typed values, not strings. `sources/itinerary.py:2344`
does `ciso8601.parse_datetime_as_naive(birth_date.text).date()` with **no** exception handling — a
`*`-masked DOB raises and aborts the whole `GetReservation` parse. Gender is compared as an `M`/`F`
code; expiry is parsed as a date-like number. All three break the caller when masked with `*`.

This is a rules + tests change. No engine, codec, or schema code changes: every action needed
already exists.

## Goals / Non-Goals

**Goals:**
- Make Sabre DOB, Gender, and card-expiry redaction format-preserving so the caller's typed parsers
  succeed on redacted responses.
- Keep these fields one-way (non-reversible) — they are not round-tripped back to the supplier.
- Lock the invariant with contract tests so a future rule edit cannot reintroduce a
  parser-breaking token.
- Record the general "typed fields must stay schema-valid" principle in the `pii-rules` spec.

**Non-Goals:**
- No new action type or engine change.
- No reversibility for DOB/gender/expiry (the caller does not need to recover them; if it ever does,
  that is a separate proposal).
- No Amadeus changes here — Amadeus typed-field parity is tracked separately (review Minor 4). The
  new `pii-rules` principle applies to it when that work lands.
- No change to the free-string fields (names, email, remarks) — `encrypt`/`mask` remain correct there.

## Decisions

**DOB → `replace` with `1901-01-01`, not `mask`.**
A masked ISO date can never be schema-valid: any mask char that survives the digit positions either
breaks `ciso8601` (`*`) or fabricates a plausible-but-wrong real date (`0000-00-00` is rejected by
ciso8601; `00`-day/month is invalid). `replace` with a fixed sentinel `1901-01-01` is unambiguously
parseable, obviously non-real (distinguishable from live data by operators), and one-way. Alternative
considered: `mask` with `mask_char:"0"` → `0000-00-00` — rejected because month/day `00` is not a
valid calendar date and ciso8601 raises. Sentinel replace is the only reliably parseable option.

**Gender → `replace` with `M`, not `remove`.**
The caller compares gender as a code. `replace` with `M` keeps a valid code present. `remove` (empty
text) was considered; rejected because an empty/absent code can trip downstream code paths that
assume the element carries a value, and `M` is the lower-risk schema-valid choice. Trade-off: every
redacted passenger reads as `M` — acceptable, gender is being deliberately destroyed, not preserved.

**Card expiry → keep `mask`, set `mask_char:"0"`.**
Expiry is numeric and length-significant; masking preserves length while destroying the value.
`0000` / `00` are valid digit strings the expiry parser accepts. `replace` was considered but `mask`
already fits (destroys value, keeps shape) and needs only the one-char param change.

**Spec placement.** Concrete field changes are MODIFIED requirements on `sabre-pii-baseline`
(the capability that owns the baked Sabre rules). The cross-cutting authoring rule is an ADDED
requirement on `pii-rules` so it governs every future ruleset, not just Sabre.

## Risks / Trade-offs

- [Sentinel DOB mistaken for real data] → `1901-01-01` is implausible as a live traveler DOB and is
  documented as the redaction sentinel; operators/tests can assert on it.
- [Contract test drift if fixture DOB format changes] → the test parses whatever the redacted fixture
  emits with the same `ciso8601` call the caller uses, so it tracks the real contract, not a hardcoded
  string.
- [Other typed fields still masked with `*` elsewhere] → out of scope for this change, but the new
  `pii-rules` requirement plus the contract-test pattern make the next occurrence catchable; Amadeus
  parity is explicitly deferred.

## Open Questions

- None blocking. Whether any other Sabre operation (beyond `GetReservationRS`) exposes typed DOB/
  gender/expiry is covered by the broader coverage work (`expand-sabre-pii-coverage`), not here.
