# Proposal: add-sabre-pii-baseline

## Why

Sabre is a configured channel type with a working credential-swap handler, but the baked ruleset
(`rules_fallback.json`) contains only Amadeus PNR rules — every Sabre response today passes through
with passenger PII (names, contact data, passport/document data, payment/FOP data, frequent-flyer
numbers) fully exposed. We now have eight representative Sabre SOAP payloads (`sabre/`) covering the
main read operations, which is enough to author a defensible baseline the same way the Amadeus
baseline was built.

## What Changes

- Add Sabre baseline PII field rules to the baked ruleset (`rules_fallback.json`), keyed
  per operation (each Sabre operation carries a different PII shape):
  - `GetReservationRS` / `stl19:GetReservationRS` (incl. deleted+active price-quote variant)
  - `TravelItineraryReadRS`
  - `GetPriceQuoteRS` (plain and with-PQR variants)
  - `AirTicketRS` (EMD)
  - Sales report (`TKT_SalesReportRS`-family with MCO)
- Rules cover: person names, emails, phones, street/city addresses, DOB, passport/document
  (APIS/SSR DOCS-style) data, payment/FOP (card numbers), frequent-flyer numbers — as element
  text **and attributes** (Sabre is attribute-heavy; the engine already rewrites attribute nodes).
- Reuse the existing rule capabilities (field rules, `mask`/`encrypt` actions, `extract_patterns`
  for free-text SSR/remark lines, `reference` rules for names echoed in free text). No rule-schema
  change is expected; if a Sabre shape proves unaddressable, a schema enhancement will be proposed
  separately rather than folded in here.
- Add sanitized Sabre fixtures under `tests/fixtures/sabre/` plus golden unit tests and
  relay-level integration tests mirroring the Amadeus baseline suites (DRY: share test helpers
  with the Amadeus golden tests where practical).
- Credential swap for Sabre (SOAP `Security` header replacement on requests, `ENC_` encryption of
  `BinarySecurityToken` in responses) **already exists** (`SabreHandler`, spec
  `channel-credential-swap`); this change only adds golden coverage against the real
  `SessionCreateRQ` / response-token shapes from the new payloads — no behavior change.

## Capabilities

### New Capabilities
- `sabre-pii-baseline`: baked baseline PII redaction rules for Sabre response operations —
  per-operation rule selection, covered PII fields, action choices (reversible encrypt vs one-way
  mask), and non-PII preservation guarantees.

### Modified Capabilities
<!-- none: rule schema, engine, and credential swap requirements are unchanged -->

## Impact

- `src/channel_relay/pii/rules_fallback.json` — new Sabre rules, bumped `rules_version`.
- `tests/fixtures/sabre/` — new sanitized operation fixtures (from `sabre/` payloads).
- `tests/unit/test_pii_sabre.py`, `tests/integration/test_pii_sabre_relay.py` — new suites.
- No engine, schema, handler, or config changes; `WP_*` compatibility untouched.
