## ADDED Requirements

### Requirement: Reservation remark PII is redacted in every history mirror

A field rule redacting remark PII with a non-encrypt action SHALL target Sabre's history mirror paths
explicitly, in addition to the remark path. Sabre re-emits each coded passenger remark up to three
times for one reservation: as `RemarkLine/Text`, as `HistoryAssociationElement`, and as
`AssociationChild`/`AssociationParent` `Content`, where the remark's `@code` becomes a `<letter>!` text
prefix. Reference rules accept only an encrypt action, so a value whose policy is one-way replacement
can never be propagated to those mirrors by the reference pass.

#### Scenario: Remark date of birth is redacted in all three renderings
- **WHEN** a `GetReservationRS` carries `BIRTHDATE-<ddmmmyy>` in a passenger remark, and the same line
  is mirrored as `P!BIRTHDATE-<ddmmmyy>` in both history renderings
- **THEN** all three occurrences carry the sentinel, and no plaintext date of birth remains in the
  response

#### Scenario: Remark passport, document dates and nationality are redacted in all three renderings
- **WHEN** a passenger remark carries `PSPT-<cc> <document number> <expiry>`, or
  `PSPT/CO-<cc>/NR-<document number>/IS-<date>/EX-<date>/CI-<cc>`, or `CTZN-<cc>`, mirrored into
  history
- **THEN** every document number, document date and country span is replaced by its sentinel in all
  renderings, while the operational markers (`PSPT-`, `/NR-`, `CTZN-`) are preserved

#### Scenario: Masked card fragment in history is redacted
- **WHEN** a form-of-payment value appears in history nodes as a supplier-masked card fragment with an
  expiry (for example `*CA<masked pan>/<mmyy>` or the `¥`-delimited remark rendering)
- **THEN** the card fragment and the expiry are both redacted in every rendering — supplier masking is
  not trusted, since it still reveals the leading digit and last four

### Requirement: Non-passenger persons in reservation free text are redacted

Each non-passenger person recorded in a `GetReservationRS` SHALL be reached by a field rule anchored on
its operational marker, so that the value also enters the collector and the reference pass scrubs its
history mirrors. These persons — emergency contact, authority-to-charge holder, travel arranger — have
no structured name node anywhere in the document, so nothing else can collect them.

#### Scenario: Emergency contact name and phone
- **WHEN** a passenger remark carries `EMER-<name>` and `EMER-<phone>`
- **THEN** the name is encrypted, the phone is redacted, and `EMER-OTHER` and other non-PII `EMER-`
  values are left untouched

#### Scenario: Authority-to-charge holder
- **WHEN** a passenger remark carries `TPREF-AUTH-AUTHORITY TO CHARGE-<name>`
- **THEN** the name is encrypted and the preference marker is preserved

#### Scenario: Travel arranger reached through the contact phone node
- **WHEN** the arranger's name is embedded in a `CTC` contact phone value (for example
  `M-<name>-<digits>`), which a separate rule masks as a whole node
- **THEN** the arranger name rule runs before the whole-node phone rule, so the name is collected and
  encrypted rather than destroyed unread, and the collected value scrubs the arranger's other
  occurrences in remarks and the ticketing comment

#### Scenario: Received-from field mixes arranger and agent
- **WHEN** `ReceivedFrom/Name` carries an arranger name, a phone number, and an agency agent name in
  one value
- **THEN** the arranger name and the phone are redacted and the agent name is preserved

### Requirement: A rewritten span must never leave a token abutting adjacent text

A rule rewriting a span inside free text SHALL NOT leave an `ENC_` token immediately adjacent to
surrounding alphanumeric or `-`/`_` text. `ENC_` payloads are base64url, so `-` and `_` read as token
characters: the greedy token scan on the request path re-consumes the adjacent text into the token, the
value never de-anonymizes, and the relay would forward a Wenrix token to the channel — breaking
transparency. Where an operational suffix would abut, the rule SHALL either fold that suffix into the
encrypted span (keeping the round-trip exact) or use a one-way sentinel containing no token characters.

#### Scenario: Phone followed by an agent name
- **WHEN** `ReceivedFrom/Name` holds a phone number followed directly by `-<agent name>`
- **THEN** the number is replaced with a one-way sentinel rather than a token, so nothing abuts the
  suffix and the response still de-anonymizes cleanly on the way back upstream

#### Scenario: Name followed by an operational qualifier
- **WHEN** a remark name is followed directly by a `-<letter>` qualifier (for example
  `TRAVEL ARRANGER/<name>-B`)
- **THEN** the qualifier is folded into the encrypted span, so the marker stays visible and
  de-anonymizing the response restores the original line byte for byte

### Requirement: Person-linked identifiers in a reservation are encrypted

Employee ids and traveller profile ids carried in a `GetReservationRS` SHALL be encrypted in every
location and namespace that mirrors them, while profile ids belonging to the agency, the corporate
account, or any other non-traveller entity SHALL be preserved.

#### Scenario: Employee id in attribute and remark
- **WHEN** an employee id appears as `Passenger/@referenceNumber` and inside a `PROFILE <org>-<id>`
  remark
- **THEN** both are encrypted with the same token

#### Scenario: Traveller profile id in both namespaces
- **WHEN** the traveller's profile id is emitted under the passenger's structured profile node and
  again in the open-reservation-element mirror namespace
- **THEN** both are encrypted, and the agency, corporate and other non-traveller profile ids for the
  same reservation are preserved
