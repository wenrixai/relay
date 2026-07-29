## ADDED Requirements

### Requirement: Visa and other-document SSR free text is redacted
For `PNR_Reply` the baseline SHALL redact the free text of `DOCO` and `DOCA` special service requests,
not only `DOCS`. `DOCO` carries visa and other-document data (visa number, place and date of issue,
destination country); `DOCA` carries a passenger address. Both SHALL be masked one-way, `DOCO`/`DOCA`
with pii type `visa`, and the structured `ssr/type` code SHALL be preserved so the anonymized PNR still
validates upstream.

#### Scenario: DOCO visa free text masked
- **WHEN** a `PNR_Reply` carries an SSR of type `DOCO` whose free text holds a visa number and issue
  data (e.g. `PHL PH/V/189200313/PH//USA//05JUN29`)
- **THEN** the free text is masked (no `ENC_` token; not reversible), the visa number does not survive,
  and `<type>DOCO</type>` is preserved

### Requirement: Given-name honorifics are redacted
For `PNR_Reply` the baseline SHALL redact the honorific (`MR`, `MRS`, `MS`, `MISS`, `MSTR`, `DR`,
`PROF`, `CHD`, `INF`, `INFT`) trailing a given name, in both `travellerInformation/passenger/firstName`
and `otherPaxNamesDetails/givenName`. A title discloses gender and, for `MRS`/`MISS`, marital status.

This supersedes the "Amadeus given-name honorific preserved" scenario added by
`expand-pnr-remark-pii-coverage`.

The honorific SHALL be redacted by a rule distinct from the name rule, and SHALL NOT be typed `person`:

- the name span must remain the value collected into the `person` bucket, or the reference pass stops
  matching the bare given name where it is echoed in remark free text;
- a title typed `person` would enter that bucket and be searched for across every remark, redacting
  unrelated occurrences.

#### Scenario: Honorific and name are separately redacted
- **WHEN** a `PNR_Reply` given-name field holds `JANGBIN MR`
- **THEN** neither `JANGBIN` nor `MR` survives, each is redacted independently, and re-sending the
  redacted body restores `JANGBIN MR`

#### Scenario: Bare given name is still scrubbed from remarks
- **WHEN** the same given name is echoed inside an RM remark free-text node
- **THEN** the reference pass still redacts it there, reusing the token the structured field received

#### Scenario: A given name with no honorific is unaffected
- **WHEN** a given-name field holds a name with no trailing title
- **THEN** the name is redacted and no honorific rule rewrites anything
