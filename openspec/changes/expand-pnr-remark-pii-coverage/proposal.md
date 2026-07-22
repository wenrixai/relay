## Why

A review of live PNR-retrieve traffic (Amadeus `PNR_Reply`, Sabre `GetReservationRS`) captured
through the relay with `pii.enabled: true` found passenger PII surviving in the redacted responses.
The structured name/email/phone fields were covered, but PII also lives in free-text remarks,
booking history, payment blocks, and contact sub-structures that the baseline rules did not target:

- **Amadeus RM remarks** — agent name lines (`NAME-JOHN/HUGH/LAFFERTY`), arrival-contact lines
  (`*ARR*LAFFERTY/JOHN*PH44-…`), and emergency-contact entries (`ECTC/TEL-…/N-FIONA LAFFERTY/…`)
  carry names and phone numbers that never appear in a structured field, so the existing reference
  pass (which only scrubs values collected from structured fields) could not see them.
- **Sabre** — `PassengerName` in the payment block, `Passengers/Name` and `Content` in history,
  `AccountingLineText`, `or114:Comment`, and `PassengerContactEmail` carried plaintext names/emails;
  contact emails also appear in a `¤`/`//`-obfuscated form the fixed-literal reference match cannot
  hit, and phone numbers hide in `CTC*` special requests, agency remarks, `ReceivedFrom`, and history
  phone nodes.

Separately, this work surfaced a latent correctness bug: because `ENC_` token payloads are base64url
(containing `-`/`_`, which read as word boundaries), a reference or extraction rule could match a
collected value *inside* a token another rule produced this pass, or leave a token directly abutting
alphanumeric free text — either of which corrupts the ciphertext so the value no longer
de-anonymizes on the way back upstream.

## What Changes

- **Broaden structured coverage (Sabre).** Encrypt `PassengerName` and `Passengers/Name`; add
  `PassengerContactEmail/Email` to the email rule; mask the history phone nodes
  (`AssociationChild[Type='PhoneNumber']/Content`, `HistoryAssociationElement[@Type='PHONE_NUMBER']`)
  as whole nodes (bounded by their tags, so no token abuts a trailing suffix such as `-W`).
- **Broaden reference coverage (Sabre).** The `GetReservationRS` reference rule now also scrubs
  collected names from `Content`, `HistoryAssociationElement`, `AccountingLineText`, and
  `or114:Comment`.
- **Add extraction rules for PII only pattern-matching can catch.** Amadeus remark name lines
  (`NAME-…`, `*ARR*…`, `/N-…`) and phone numbers; Sabre `¤`/`//`-obfuscated contact emails, `CTC*`
  special-request phones, agency-remark phones, corporate booking-tool traveller ids, and
  `ReceivedFrom` embedded phones.
- **Keep honorifics.** Amadeus given-name fields encrypt only the name, leaving the trailing
  honorific (`MR`/`MS`/…) as non-PII operational text — and so the bare given name lands in the
  reference bucket and is scrubbed from remark free text too.
- **Shield existing tokens (correctness fix).** Extraction and reference matching now skip any span
  overlapping an `ENC_` token already present in the node, so no rule rewrites part of a token.

Known limitation (documented, not fixed here): a name glued into an alphanumeric agency code with no
word boundary (for example `*13-JLASTFIRST`) is not scrubbed — substring matching there would abut a
token against trailing text. The word-boundary default in the referential-redaction spec is retained
deliberately to avoid over-redaction.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `pii-rules`: the baked Amadeus/Sabre baseline gains remark/history/contact field, extraction, and
  reference rules; Amadeus given-name rules extract the name and preserve the honorific; Sabre history
  phone nodes are masked as whole nodes.
- `referential-redaction`: extraction and reference matching SHALL never rewrite content inside an
  existing `ENC_` token.
