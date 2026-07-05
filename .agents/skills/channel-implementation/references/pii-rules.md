# PII Rule Authoring

## Purpose

How to turn a payload analysis into correct entries in
`src/channel_relay/pii/rules_fallback.json`, using only the capabilities the engine already has.
The schema (`src/channel_relay/pii/rules.py`) and engine (`src/channel_relay/pii/engine.py`)
have covered every supplier shape seen so far (Amadeus, Sabre) — reach for a schema change only
after exhausting the levers below, and then via a separate OpenSpec proposal.

## 1. What a rule can do (capabilities inventory)

Field rule (flat wire format; `rule_type` defaults to `field`):

```json
{
  "id": "sabre.res.email",
  "channel": "sabre",
  "operation": "^GetReservationRS$",
  "path": "//s19:EmailAddress/s19:Address | //o14:Email/o14:Address",
  "namespaces": {"s19": "http://webservices.sabre.com/pnrbuilder/v1_19",
                 "o14": "http://services.sabre.com/res/or/v1_14"},
  "pii_type": "email",
  "method": "encrypt"
}
```

- `operation` is a **regex** matched against the body-derived operation — the main DRY lever.
- `path` is namespace-aware XPath; **unions (`|`) are allowed** — one rule, many locations.
- XPath may select **attributes** (`//p:NameAssociation/@firstName`) — the engine rewrites
  attribute values via lxml smart strings, same as element text.
- Predicates work: `//o14:ServiceRequest[@code='DOCS' or @code='DOCO']/o14:FreeText`.
- `method`: `encrypt` (reversible `ENC_` token), `mask` (`mask_char`, `keep_prefix`),
  `replace` (`replacement`), `remove`.
- `extract_patterns`: regexes applied inside the selected value; exactly one capture group →
  only that span is rewritten, surrounding text preserved. Example — a card BIN echoed in fee
  text: `{"pattern": "BEGINS WITH (\\d{6})"}`.
- `ignored_content_patterns`: skip values matching these regexes.
- `required: true`: rule failing to match/rewrite anything fails the whole redaction (502) —
  use for fields that must exist on an operation.

Reference rule (`rule_type: "reference"`): phase 2 — searches its target nodes' text for
values that field rules collected in phase 1 (grouped by `source_pii_types`), encrypting each
occurrence in place. Guards: `min_match_len` (default 3), `word_boundary` (default true).
Use for remarks / special-service-request lines / e-ticket free text where PII is echoed amid
operational text you must preserve.

`pii_type` scope (see `PiiType`): person, dob, gender, nationality, passport_id, visa, phone,
email, address, payment, frequent_flyer. **Not PII** — do not redact: record locators, ticket
and invoice numbers, amounts/currency, agent sign-in codes, pseudo-city codes, seats, segments,
message-header routing identifiers.

## 2. Action policy (mirror it for new channels)

- `encrypt` (reversible) — values a client legitimately round-trips or correlates: names,
  emails, frequent-flyer numbers, supplier session tokens.
- `mask` (one-way) — identity documents (date of birth, gender, passport/visa data), phones,
  address lines, payment data (card numbers, expiry, bank identification numbers).
- Supplier pre-masked values (e.g. `4XXXXXXXXXXX4848`) still get redacted — they reveal the
  card's first digit and last four, and trusting supplier masking imports someone else's policy.

## 3. Conventions

- Rule ids: `<channel>.<operation-group>.<field>` (e.g. `sabre.pq.name_attributes`).
- One rule per concern; use XPath unions rather than near-duplicate rules; use operation
  alternation (`^(GetPriceQuoteRS|GetReservationRS)$`) when the same structure is embedded in
  several operations.
- Declare every prefix a rule's XPath uses in its own `namespaces` map — supplier payloads use
  default (unprefixed) namespaces, so you must bind your own prefixes. An undeclared prefix is
  a silent no-match, not an error.
- Bump `rules_version` (`<channels>-baseline-<date>`) on every rules change; a test asserts
  the channel is represented in the version string.

## 4. Pitfalls (each one cost a debugging round — check them against fixtures, not analysis notes)

1. **Near-identical element variants.** Sabre uses BOTH `GenericSpecialRequest` (singular)
   and `GenericSpecialRequests` (plural) as free-text parents in the same schema family, and
   mirrors most passenger data in a parallel `or114` history namespace. Grep the actual
   fixture for every element name before trusting a payload-analysis summary.
2. **Word-boundary blindness in reference rules.** A collected value embedded with an
   alphanumeric character touching it (card number in `*VI4XXX…` remark) will NOT match a
   word-bounded reference rule. If a node is categorically sensitive (form-of-payment remarks),
   mask it wholesale with a targeted field rule (`//s19:Remark[@type='FOP']//s19:Text`) instead
   of loosening `word_boundary`.
3. **Reference rules only see collected values.** PII appearing exclusively in free text (never
   in a structured node) is invisible to phase 2. Give it a field rule with `extract_patterns`,
   or a structured sibling rule that collects it.
4. **Free text mirrors structured data.** Identity-document lines (`DOCS DL HK1/DB/…`) appear
   as structured children AND as `FreeText`/`FullText` siblings AND in history mirrors — cover
   all three or the masked value survives elsewhere.
5. **Both text and attributes.** The same supplier often puts names in element text in one
   structure and in `@firstName`/`@lastName` attributes in another (embedded price-quote
   blocks). Sweep for both.
6. **Don't redact operational identifiers.** Encrypting locators/ticket numbers breaks client
   workflows and violates the PII scope (§7); golden tests must assert they survive verbatim.

## 5. Verify empirically before writing tests

Drive the real engine against the sanitized fixture in a scratch script:

```python
from channel_relay.pii.engine import redact_response_body
redacted, counts = redact_response_body(body, channel="<channel>", ruleset=ruleset, keyring=keyring)
```

Then grep `redacted` for every planted fake PII value — anything that survives means a wrong
XPath/namespace (silent no-match), not an engine error. `counts` (per-`pii_type` rewrite
counts) become golden-test assertions.
