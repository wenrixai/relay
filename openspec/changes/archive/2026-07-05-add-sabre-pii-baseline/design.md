# Design: add-sabre-pii-baseline

## Context

The PII engine (Slice 2) is channel-agnostic: rules select on `channel` + `operation` regex,
locate nodes via namespace-aware XPath, and rewrite element text **and attribute values**
(`_rewrite_node` handles lxml smart-string attribute results). The baked fallback currently ships
only the Amadeus `PNR_Reply` baseline. Sabre credential swap already exists (`SabreHandler`:
request SOAP `Security` fragment replacement, response `BinarySecurityToken` → `ENC_` token) and is
spec'd in `channel-credential-swap` — it is reused, not rebuilt.

Eight real Sabre payloads (`sabre/`) were analyzed. Findings that drive the design:

- Operation = SOAP Body first-child local-name (`GetReservationRS`, `TravelItineraryReadRS`,
  `GetPriceQuoteRS`, `AirTicketRS`, `DailySalesReportRS`); matches the engine's existing
  `parse_operation`.
- Sabre splits PII between element text (stl19/or114/sabreXML) and attributes (pqs name
  attributes, `Card/@number`, `Ticketing/@eTicketNumber`) — attribute rewriting is mandatory.
- The pqs `PriceQuoteInfo` structure appears both as the `GetPriceQuoteRS` payload and embedded
  inside `GetReservationRS` — a single shared rule with an operation alternation covers both.
- Free text (remarks, SSR `FreeText`/`FullText`, OB-fee descriptions) can echo structured PII
  (names, BIN) — referential rules + one extract pattern handle this.
- `session_create_request.xml` confirms the request credential shape the existing
  `soap_security` fragment swap already replaces (`wsse:UsernameToken` with unqualified
  `Organization`/`Domain` children); response files confirm `BinarySecurityToken` as the session
  secret the handler already encrypts.

## Goals / Non-Goals

**Goals:**
- Baseline field + reference rules for the five observed Sabre response operations, baked into
  `rules_fallback.json` (single ruleset document, bumped `rules_version`).
- Golden coverage from sanitized fixtures for every covered operation, mirroring the Amadeus
  golden-test approach; DRY shared helpers between the Amadeus and Sabre suites.
- Integration coverage proving pipeline order on Sabre: response credential cleanup
  (`BinarySecurityToken`) then PII redaction, and request de-anonymization then security-header
  swap.

**Non-Goals:**
- No rule-schema, engine, or handler changes — analysis found no Sabre shape the current
  capabilities (attribute XPath, extract patterns, reference rules, operation regex) cannot
  express. If implementation disproves this, that becomes a separate proposal.
- No redaction of operational identifiers (locators, ticket numbers, agent sines, PCC, amounts) —
  out of PII scope per `PiiType` (§7).
- No Sabre request-side PII rules (requests carry `ENC_` tokens handled by the generic
  de-anonymizer) and no new channel configuration.

## Decisions

1. **Rule granularity: per-operation rule groups + shared-pattern rules.** IDs follow
   `sabre.<op>.<field>` (mirrors `amadeus.pnr.*`). Cross-operation patterns get one rule with an
   operation alternation, e.g. `^(GetPriceQuoteRS|GetReservationRS)$` for pqs name attributes —
   the DRY lever the schema already provides (operation is a regex). Alternative — duplicating
   rules per operation — rejected: more rules to keep consistent, no expressiveness gain.
2. **Namespace strategy: per-rule explicit prefixes.** Sabre uses default namespaces heavily;
   each rule declares exactly the prefixes its XPath uses (e.g. `s19` → pnrbuilder v1_19, `p` →
   pqs/1.0, `o14` → or/v1_14, `t3` → tir/v3_10, `sx` → sabreXML/2011/10, `at` → air/ticket/v1).
   Unqualified children inside qualified parents (seen in the security header) are irrelevant to
   response rules; body payloads are consistently namespaced.
3. **Action policy mirrors the Amadeus baseline.** Reversible `encrypt` for values a client
   round-trips or correlates (names, emails, frequent-flyer numbers); one-way `mask` for
   identity-document/contact/payment detail the client never needs back (DOCS/DOCO, phones,
   address lines, card numbers, expiry, BIN). Rationale: encrypt-by-default maximizes utility;
   mask where re-exposure risk outweighs it — same trade-off already made for Amadeus.
4. **Free text via `reference` rules, not blanket masking.** Remarks/SSR text carries operational
   content (ticketing advisories, invoice codes) that blanket masking would destroy. Reference
   rules encrypt only values collected by structured rules in the same pass. Exception: the
   OB-fee BIN echo uses a `field` rule with an `extract_pattern` (`BEGINS WITH (\d{6})`) because
   the BIN in `Description` must be caught even though `BankIdentificationNumber` is its own node
   (collector-based reference matching also covers it, but the extract rule is deterministic and
   testable in isolation). Likewise, `Remark[@type='FOP']` lines are masked wholesale by a field
   rule: they embed the card number with an alphanumeric `*VI` prefix touching it, which the
   reference rule's word-boundary guard correctly refuses to match — and an FOP remark is
   payment data in its entirety.
5. **Pre-masked supplier values still redacted.** `CardNumber` `4XXXXXXXXXXX4848` reveals BIN +
   last4; treat as payment PII (mask fully). Trusting supplier masking would encode an external
   system's policy into ours.
6. **Fixtures are sanitized copies of `sabre/` payloads.** Real names/emails/phones/card
   fragments/FF numbers/tokens replaced with fake-but-shape-identical values (as done for the
   Amadeus fixture); the oversized `DailySalesReportRS` is truncated to a handful of
   `IssuanceData` records to keep tests fast. Raw `sabre/` files never enter the test tree or
   git history unsanitized.
7. **Test DRY: extract shared golden helpers.** `_texts`/keyring/ruleset fixtures currently local
   to `test_pii_amadeus.py` move to a shared `tests/unit/pii_golden.py` (or conftest) consumed by
   both channel suites. Alternative — copy-paste per channel — rejected per repo DRY rule.

## Risks / Trade-offs

- [XPaths validated against 8 fixtures may miss variants in other Sabre versions/operations] →
  baseline is explicitly versioned (`rules_version`); rules API can supersede it without a code
  change; uncovered operations fail open by design (documented in the spec as no-rules behavior).
- [Reference rules only catch free-text PII that structured rules collected first] → accepted v1
  limitation, identical to the Amadeus/referential-redaction trade-off; blanket masking of
  operational text is worse.
- [Attribute-heavy rules exercise the smart-string path more than any existing ruleset] → golden
  tests assert attribute rewrites and round-trips explicitly; engine code is untouched.
- [Sales report fixture is ~2k lines / ~230 records] → truncate fixture; count assertions use the
  truncated totals.

## Migration Plan

Additive rules + tests only; ships in the baked bundle at next image build. Rollback = revert the
`rules_fallback.json` entries. No config, schema, or key changes.

## Open Questions

- None blocking. If Sabre `TravelItineraryReadRS` unredacted samples surface later (current
  fixture is pre-redacted upstream), tighten its rules in a follow-up.
