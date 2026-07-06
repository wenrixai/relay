# Sabre Integration Review — Relay Gaps & Required Changes

**Audience:** wenrix-proxy (channel relay) team
**Scope:** Compatibility of the relay's PII redaction and credential swap with the Wenrix Sabre service (`wenrix` repo, `src/themes/channels/services/sabre/`). Relay API authentication is explicitly out of scope.
**Goal:** The relay must be *transparent* to the Wenrix Sabre service — no behavioral change visible to the caller beyond PII tokenization, and no supplier-visible change beyond credential substitution.

**Verdict:** The pipeline architecture is sound (de-anonymize → credential swap → response credential cleanup → redaction, fail-closed error contract). However, as implemented today, the Sabre channel is only transparent in pure pass-through mode (no `credentials` configured, PII limited to the five covered operations). Two blockers and three significant gaps must be fixed before enabling credential swap + PII for Sabre production traffic.

---

## Background: how the Wenrix Sabre service talks to Sabre

Understanding the caller is essential to every finding below.

1. **Session-stateful SOAP.** The service authenticates once per session via `SessionCreateRQ` (or `TokenCreateRQ` for sessionless ATK tokens) using a `Security/UsernameToken` header (username, password, IPCC, client id/secret). Sabre returns a `BinarySecurityToken`. **Every subsequent call** sends `Security/BinarySecurityToken` — never `UsernameToken` again. See `wenrix` repo: `src/themes/channels/services/sabre/api.py` (`_create_security_header`, lines 268–294) and the full session lifecycle in `token_manager.py` (acquire → context change → ignore transaction → session close). Sessions are pooled, reused across requests, and carry PNR context state.
2. **Compressed responses.** The search flow requests compression (`handlers/search.py:40`, `compress=True`). Sabre then wraps the response body in a `<CompressedResponse>` element containing **base64-encoded gzip** XML. The Wenrix side decodes it after receipt (`sources/sabre_api.py:227–229`). This is application-level compression inside the XML — unrelated to HTTP `Content-Encoding`, which httpx already handles.
3**~50 supported operations.** `sources/sabre_api.py` registers ~50 request/response API pairs, including PNR creation, ticketing, refunds, exchanges, queues, history, sales reports, and free-text cryptic commands (`SabreCommandLLS`).
4**Typed response parsing.** Responses are parsed into typed models with strict converters — e.g. dates via `ciso8601.parse_datetime_as_naive(...)` with no error handling in several places. A field whose value the relay replaced with an `ENC_` token will crash parsing if the caller expects a date/number.
5. **Error handling.** Wenrix retries HTTP 500/502/503/504/599 up to 3× (`api.py:40–51`) and, on unparseable bodies, surfaces a generic `SabreFault("Response format is incorrect")`.

---

## Blocker 1 — Credential swap destroys the Sabre session token

### Problem

`SoapSecurityHandler.swap_request_body` (`src/channel_relay/channels/handlers.py:276–283`) unconditionally replaces the **entire** `Security` element with the static `soap_security` fragment from config, on **every** request.

This is correct for the first call of a session (`SessionCreateRQ` carries `UsernameToken` — the credential we want to substitute). It is wrong for every other call: after de-anonymization restores the real `BinarySecurityToken` (round-tripped as an `ENC_` token, per the response cleanup in `SabreHandler.swap_response`), the swap stage throws the live session token away and forwards a static fragment instead.

The integration test encodes this behavior as *expected*:

> `tests/integration/test_pii_sabre_relay.py::test_encrypted_token_round_trips_on_next_request` (lines 96–115) asserts that the follow-up `GetReservationRQ` reaches the channel with `>RELAY<` (the static fragment) instead of the restored session token.

Against real Sabre this fails: stateful operations (GetReservation, EnhancedAirBook, EndTransaction, ContextChange, queue operations, ticketing…) require the `BinarySecurityToken` issued at session creation. A static config fragment can never be a valid dynamic session token. Sabre will reject the request or, worse, behave unpredictably.

`soap_security_target_xpath` does not rescue this: pointing it at `Security/UsernameToken` makes follow-up requests (which have no `UsernameToken`) fail with `CredentialSwapError` → 502, because `_security_target` treats a missing target as an error (`handlers.py:300–319`).

Note the same analysis applies to Amadeus stateful sessions (`SessionId`/`SequenceNumber`/`SecurityToken` header round-trip) — verify separately.

### Required change

Make the Sabre (and Amadeus/Travelport session-mode) swap **token-aware**:

1. In `SabreHandler.swap_request_body`, inspect the located `Security` element **after** de-anonymization has run (pipeline order already guarantees this — forwarder stage [7] before [8b]).
2. If `Security` contains a `BinarySecurityToken` child with non-empty text → **do not replace anything**; return `False` (no change). The de-anonymized token must pass through verbatim.
3. If `Security` contains a `UsernameToken` (or is empty/absent-of-token) → replace with the configured fragment as today.
4. Update `test_encrypted_token_round_trips_on_next_request` to assert the opposite of what it asserts now: the forwarded follow-up must contain the decrypted real token (`SANITIZED!...`-style fixture value), not `>RELAY<`, and no `ENC_` string.
5. Add a test for the mixed case: request carrying a plaintext (non-`ENC_`) `BinarySecurityToken` — e.g. the caller replays a token when PII was disabled — must also pass through.

Sketch:

```python
@dataclass(frozen=True, slots=True)
class SabreHandler(SoapSecurityHandler):
    channel_type: ChannelType = ChannelType.SABRE
    response_auth_local_names: ClassVar[set[str]] = {"BinarySecurityToken"}
    session_token_local_names: ClassVar[set[str]] = {"BinarySecurityToken"}

    def swap_request_body(self, root, context) -> bool:
        credentials = context.channel.credentials
        if not credentials:
            return False
        target = self._security_target(root, credentials)
        if self._holds_session_token(target):
            return False  # live session — token must reach the channel untouched
        _replace_with_fragment(target, _require_credential(credentials, "soap_security"))
        return True

    def _holds_session_token(self, security: etree._Element) -> bool:
        return any(
            isinstance(child.tag, str)
            and _local_name(child) in self.session_token_local_names
            and (child.text or "").strip()
            for child in security.iter("*")
        )
```

---

## Gap 3 — PII rule coverage: 5 of ~50 Sabre operations

### Problem

`src/channel_relay/pii/rules_fallback.json` contains 24 Sabre rules covering exactly five response operations:

| Covered | PII handled |
|---|---|
| `GetReservationRS` | names, email, phone, address, DOB, gender, docs, FF, cards, remarks |
| `GetPriceQuoteRS` | name attributes, card/BIN |
| `AirTicketRS` | name |
| `DailySalesReportRS` | person name |
| `TravelItineraryReadRS` | passenger data |

The Wenrix service uses ~50 operations (`sources/sabre_api.py:123–180`). Uncovered PII-bearing responses pass to the caller **in plaintext, silently** — `select_rules` returning an empty list is indistinguishable from "nothing to redact" (`engine.py:213–230`).

High-priority uncovered operations (all actively used by Wenrix handlers):

| Operation (RS) | PII exposure |
|---|---|
| `CreatePassengerNameRecordRS` | echoes full traveler itinerary incl. names after PNR create |
| `PassengerDetailsRS` | echoes names, contact details |
| `TravelItineraryHistoryRS` | history entries with names, FOP remarks |
| `GetTicketingDocumentRS` / `eTicketCoupon` (`GetETicketDetailsRS`) | passenger name on ticket, FOP |
| `GetElectronicDocument` (`GetTicketInformationFromAirlineRS`) | passenger name, document data |
| `Refund` (`TicketRefundRS`) / `AutomatedExchanges` (`TicketExchangeRS`) | name, FOP, card data |
| `DailyRefundReportRS` | names, document numbers |
| `Trip_Search` (`PastDatePnrDetailsRS`) | past PNR passenger data |
| `QueueAccessRS` | queued PNR list with names |
| `SabreCommandRS` | **free-text cryptic screen dumps** — a `*R` display is an entire PNR (names, phones, FOP, remarks) as text |

### Required changes

1. **Author field rules for every operation above** (except `SabreCommandRS`, below). Source the XPaths from the Wenrix parsing models — `sources/itinerary.py`, `ticketing.py`, `pnr.py`, `history.py`, `queue.py`, `sales_report.py` in the Wenrix repo enumerate exactly which elements/attributes carry names, documents, and payment data (those files are the de-facto schema of what the caller reads).
2. **`SabreCommandRS`:** structured rules cannot work on cryptic screens. Options, in order of preference:
   a. Per-channel config flag to **block** `SabreCommandLLS` when PII is enabled (fail closed, explicit).
   b. Regex-based reference redaction over the screen text (name patterns like `1.1LASTNAME/FIRSTNAME`, card patterns) — best-effort, must be labeled as such.
   c. Pass-through with an explicit, logged, per-channel opt-in (`allow_unredacted_operations: ["SabreCommandLLS"]`).
   Silent pass-through (today's behavior) is not acceptable.
3. **Make coverage failure visible.** Add a per-channel config knob:
   ```json
   "pii": { "enabled": true, "uncovered_operation": "block" | "warn" | "allow" }
   ```
   - `block`: response operation with zero matching rules → 502 `pii_redaction_failed` (safe default for channels claiming full PII protection).
   - `warn`: forward but emit a dedicated metric + log (`pii_uncovered_operation{channel, operation}`) so gaps are discoverable instead of silent.
   Wire an allowlist for genuinely PII-free operations (`SessionCreateRS`, `EndTransactionRS`, `QueueCountRS`, `DisplayCurrencyRS`, …) so `block` mode is operable.
4. **Use `required: true`** on the anchor rule of each PII-heavy operation (e.g. the passenger-name rule in `GetReservationRS`) so schema drift (Sabre version bumps changing element names) fails closed instead of leaking. Today no Sabre rule sets `required`.

---

## Gap 4 — Encrypting typed fields crashes the caller's parsers

### Problem

Several fallback rules encrypt values the Wenrix parser consumes as **typed** data, not opaque strings:

- `sabre.res.docs_dob` — Wenrix parses `Docs/DateOfBirth` with `ciso8601.parse_datetime_as_naive(birth_date.text).date()` at `sources/itinerary.py:2344–2346` **with no exception handling**. An `ENC_…` token here raises and kills the whole `GetReservation` parse. (A second DOB path at `itinerary.py:1972` is guarded and degrades to `None`.)
- `sabre.res.docs_gender` — parsed/compared as a code (`M`/`F`) in passenger models.
- `sabre.pq.card_expiry` / `sabre.res.card_expiry` — expiry parsed as a date-like value in FOP handling.

General principle violated: **redaction must be format-preserving for any field the caller parses as a non-string type.** `encrypt` is only transparent for free-string fields (names, emails, addresses, remarks).

### Required changes

1. **Change actions for typed fields** in the Sabre ruleset:
   - DOB → `replace` with a fixed valid sentinel date (`1901-01-01`) **or** `mask` preserving the format. If reversibility is required, pair the replace with an `encrypt` rule that moves the real value into a string-safe location — but the simplest correct model is: DOB is one-way redacted, callers that need it must not (they get the sentinel).
   - Gender → `replace` with a fixed valid code (`M`), or `remove` if the schema marks it optional.
   - Card expiry → `mask` keeping the format (`keep_prefix: 0`, mask char `0` → e.g. `0000-00`), never `encrypt`.
2. **Add a rules-authoring guideline** to the PII docs: *before choosing `encrypt` for a field, confirm the consuming parser treats it as an opaque string; date/number/enum-typed fields must use `replace`/`mask` with schema-valid output.* The Wenrix `sources/*.py` converters are the reference for Sabre.
3. **Add a contract test per typed field**: run the redacted fixture through a minimal type-check (ISO-date parse of every `DateOfBirth`, Luhn-shaped mask of card fields) so a future rule edit cannot reintroduce a parser-breaking token.

---

## Gap 5 — Non-deterministic tokens break value equality across responses

### Problem

`encrypt` uses a random 96-bit IV per call (`codec.py:49`), so the same plaintext yields a **different** `ENC_` token on every occurrence — across responses and even between two fields in the same response.

Caller impact: any logic comparing PII values by equality stops working — matching a passenger between `GetReservationRS` and `GetPriceQuoteRS`, deduplicating names, correlating a refund document to a passenger. Flows keyed on structural identifiers (name numbers like `1.1`, ticket numbers, PNR locators) are unaffected. The Wenrix Sabre code does both; the name-equality paths silently degrade (wrong matches / no matches), which is worse than crashing.

Note the *reference-rule* mechanism already assumes intra-response value correlation matters (it hunts collected plaintext in free text) — but it re-encrypts each hit with a fresh IV, so even intra-response, two occurrences of `SMITH` become two different tokens.

### Required changes

1. **Offer a deterministic encryption mode** per pii_type (or per rule): `"deterministic": true` → AES-SIV (RFC 5297; `cryptography` ships `AESSIV`) with a per-epoch SIV key derived from the keyring (e.g. HKDF of the epoch key with a `"siv"` info label). Same plaintext + same epoch → same token; equality is preserved for the caller.
   - Trade-off to document: deterministic encryption reveals equality patterns (same passenger recognizable across responses). That is precisely the property the caller needs; it is an accepted, bounded leak. Keep random-IV CTR as the default; enable SIV only for `person` (and any other type the caller correlates).
   - Control-byte headroom exists: bits 5–7 are reserved (`codec.py:26–28`) — allocate one as the "deterministic/SIV" flag so `decrypt` can route to the right primitive and old tokens stay valid.
2. **Reference rules must reuse the phase-1 token** for the same plaintext within a response (cache `plaintext → token` in the collector) regardless of mode — cheap, no crypto change, fixes intra-response consistency immediately.
3. Coordinate with the Wenrix team on which pii_types actually need equality; do not enable SIV wholesale.

---

## Minor items (quick wins)

1. **Error contract vs caller retries.** Relay fail-closed errors are deterministic 502s with `X-Wenrix-Error`; the Wenrix client retries 502 3× (`api.py:40–51`) before surfacing a generic parse error. No relay change strictly needed, but: (a) confirm 502 is intentional for *deterministic* failures — 422/400 would stop pointless retries, though it changes the documented contract; (b) at minimum, keep `X-Wenrix-Error` stable — the Wenrix side will be updated to read it and skip retries.
2. **`max_inspect_bytes` (8 MiB, `settings.py:29`).** Large uncompressed `GetReservationRS`/BFM responses can exceed this → 413 to the caller mid-flow. Make the cap per-channel-overridable and emit a metric on 413 so sizing is tunable from data. When implementing Blocker 2, remember the cap must apply to *inflated* `CompressedResponse` bytes.
3. **Document the transparent baseline.** `docs/CREDENTIAL_SWAP.md` should state explicitly: a Sabre channel with empty `credentials` and `pii.enabled: false` is byte-transparent apart from header hygiene — that is the safe rollout starting point, with credential swap and PII enabled per the fixes above.
4. **Amadeus parity check.** Every finding here (session-token-aware swap, coverage policy, typed fields, determinism) applies structurally to the Amadeus handler (`SessionId`/`SequenceNumber`/`SecurityToken`). Run the same review before enabling that channel.

---

## Priority order

| # | Item | Severity | Effort (rough) |
|---|---|---|---|
| 1 | Blocker 1: token-aware Security swap | Blocker — breaks all stateful traffic | Small (handler + 2 tests) |
| 2 | Gap 4: typed-field actions (DOB/gender/expiry) | High — crashes caller parsing | Small (rules only) |
| 3 | Gap 3: coverage policy (`block`/`warn`) + `SabreCommandRS` decision | High — silent PII leak | Medium |
| 4 | Gap 3: author rules for the 10 uncovered operations | High | Large (needs fixtures) |
| 5 | Gap 5: intra-response token reuse in reference rules | Medium | Small |
| 6 | Gap 5: deterministic (SIV) mode for `person` | Medium — needs Wenrix input | Medium |
| 7 | Minor 1–4 | Low | Small |

Items 1 + 3 + 6 are pure code/rules changes with existing test scaffolding — ship those first. Item 2 unblocks the search flow. Items 4–5 need coordination with the Wenrix channels team for fixtures and the PII-free allowlist.
