## Why

Several Sabre baseline rules redact values that the Wenrix caller parses as **typed** data
(dates, enum codes), not opaque strings. The current `mask` action replaces the value with the
mask character `*` (e.g. `1994-07-01` → `**********`, `M` → `*`, expiry `12` → `**`). The Wenrix
parser feeds `DateOfBirth` straight into `ciso8601.parse_datetime_as_naive(...)` with no exception
handling (`sources/itinerary.py:2344`), so a masked value raises and kills the entire
`GetReservation` parse — the response is unusable and surfaces as a generic `SabreFault`. Gender and
card-expiry are consumed the same way. Redaction must be **format-preserving** for any field the
caller reads as a non-string type.

## What Changes

- Change the Sabre `DateOfBirth` (`sabre.res.docs_dob`) redaction from `mask` to `replace` with a
  fixed, schema-valid sentinel date `1901-01-01` — one-way, still non-reversible, but parseable.
- Change `Gender` (`sabre.res.docs_gender`) from `mask` to `replace` with a fixed valid code `M`.
- Keep card expiry (`sabre.res.card_expiry`) as `mask` but set `mask_char: "0"` so
  `ExpiryMonth`/`ExpiryYear` stay numeric (`12` → `00`, `2027` → `0000`).
- Add a general rules-authoring requirement: `encrypt`/`mask` (with a non-schema-valid mask char)
  are only safe for free-string fields; date/number/enum-typed fields MUST use `replace`/`mask`
  that emits schema-valid output.
- Add contract tests that parse every typed redacted fixture value (ISO-date parse of each
  `DateOfBirth`, numeric check of expiry) so a future rule edit cannot silently reintroduce a
  parser-breaking token.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `sabre-pii-baseline`: DOB and Gender move from one-way `mask` to schema-valid `replace`; card
  expiry masks with a numeric mask char instead of `*`.
- `pii-rules`: adds a normative format-preservation constraint on action choice for typed fields.

## Impact

- `src/channel_relay/pii/rules_fallback.json` — three rule entries edited (`sabre.res.docs_dob`,
  `sabre.res.docs_gender`, `sabre.res.card_expiry`).
- `tests/` — new typed-field contract tests over sanitized Sabre fixtures.
- No engine, codec, or schema code changes: `replace` and `mask` (`mask_char`) already exist.
- No `WP_*` config surface change; no breaking change.
