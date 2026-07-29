## Why

QA verification of CERT PNR-retrieve traffic (2026-07-29) found passenger PII surviving in redacted
responses across three defects. All three are coverage gaps in the baked baseline ruleset, not engine
bugs:

- **Sabre `GetReservationRS` (PNR TORIWF)** — the APIS travel-document block leaks the passport
  number and its expiry date. `sabre.res.travel_document_number` only targeted
  `//o14:OtherSupplementaryInformation/o14:DocumentNumber`, so the `DocumentNumber` carried by
  `s19:DOCSEntry` and by the `o14:TravelDocument` history mirror was never located, and no rule
  targeted `DocumentExpirationDate` at all. The same block also carries the passport's country of
  issue and nationality in the clear.
- **Amadeus `PNR_Reply` (PNR ZFJH2Z)** — the honorific survives in given-name fields
  (`<firstName>REDACTED MR</firstName>`). Preserving it was a deliberate decision in
  `expand-pnr-remark-pii-coverage`; a title discloses gender and, for `MRS`/`MISS`, marital status,
  so that decision is reversed here.
- **Amadeus `PNR_Reply` (PNR 73EXIH)** — visa data in a `DOCO` SSR free-text node
  (`PHL PH/V/189200313/PH//USA//05JUN29`) is untouched. `amadeus.pnr.ssr_docs` matches
  `a:type='DOCS'` only; Sabre already covers `DOCS`/`DOCO`/`DOCA` together.

QA additionally reported `DateOfBirth` and `Gender` as unredacted. Those rules did fire — the reported
`1901-01-01` and `M` are the `replace` sentinels. The report does, however, expose a real adjacent
defect: `sabre.res.docs_dob` wrote the ISO sentinel into `//o14:TravelDocument/o14:DateOfBirth`, whose
native format is `DDMMMYYYY` (`01JAN1990`). Emitting an ISO date into a node that namespace never
expresses in ISO breaks the typed-field contract and is why QA read a sentinel as live data.

The gaps went undetected because the sanitized fixtures did not carry the leaking nodes: the
`DOCSEntry` and `TravelDocument` blocks in `get_reservation_pq_history_response.xml` had no
`DocumentNumber`, `DocumentExpirationDate`, or country children, and the Amadeus fixture had no `DOCO`
SSR. The fixtures are extended first so the golden suites reproduce each leak before any rule changes.

## What Changes

- **Sabre passport number.** Widen `sabre.res.travel_document_number` to the union of
  `o14:OtherSupplementaryInformation`, `s19:DOCSEntry`, and `o14:TravelDocument` `DocumentNumber`
  nodes; masking is unchanged.
- **Sabre passport expiry.** Add expiry rules with format-matched, schema-valid sentinels — the
  `s19` node is replaced with an ISO date, the `o14` mirror with `DDMMMYYYY`.
- **Sabre date-of-birth format (correctness fix).** Split `sabre.res.docs_dob` so each namespace
  receives a sentinel in the format that namespace actually emits, instead of forcing ISO on both.
- **Sabre passport nationality.** Redact the passport's country of issue and nationality country in
  both namespaces with a schema-valid two-letter literal. First use of the `nationality` `pii_type`,
  which the model already defines.
- **Amadeus visa SSR.** Add a `DOCO`/`DOCA` SSR free-text rule typed `visa`, mirroring Sabre.
- **Amadeus honorific (reverses a prior decision).** Given-name honorifics are now redacted by a
  dedicated rule typed `gender`, alongside the existing name-extraction rule. Two rules rather than a
  wider pattern on one: the name must stay the value collected into the `person` bucket, or the
  reference pass stops matching the bare given name in remark free text, and the honorific must stay
  out of that bucket so short titles are never searched for across remarks.

Scoped to `GetReservationRS`. `Trip_SearchRS` (`sabre.trip.*`) and `TravelItineraryHistoryRS`
(`sabre.itinhist.*`) carry the same passport gap and are deliberately left for a follow-up change.

This supersedes the "Keep honorifics" decision and its scenario in
`expand-pnr-remark-pii-coverage`.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `sabre-pii-baseline`: the `GetReservationRS` baseline SHALL redact the travel-document number,
  expiry date, and nationality/country-of-issue in both the `s19` structured block and the `o14`
  history mirror, and typed date sentinels SHALL match the format of the node they replace.
- `amadeus-pii-baseline`: the `PNR_Reply` baseline SHALL redact `DOCO`/`DOCA` SSR free text and the
  honorific in given-name fields.
