## Why

Golden-fixture review found plaintext PII surviving the baked fallback rules even though the
existing channel tests pass:

- Travelfusion phone rules select complex phone containers, encrypting indentation while leaving
  the actual phone components plaintext. Traveller DOB, age, title, custom passport/loyalty values,
  fax numbers, and the client IP diagnostic value are also uncovered.
- Farelogix redacts structured DOB, gender, and document number fields but leaves DOB/gender in a
  `DOCS` SSR and leaves document issue/expiry metadata and passenger titles plaintext.
- Travelport address redaction omits the state/province component.

These are baked-rule and golden-test gaps. No engine retry, parsing, or request behavior changes are
needed.

## What Changes

- Target Travelfusion phone leaf values, including fax, rather than their parent containers.
- Encrypt Travelfusion traveller DOB, age, title, sensitive custom supplier parameters, and client IP
  values, preserving the channel's reversible-encryption policy.
- Add `age` and `ip_address` to the PII type vocabulary so metrics do not misclassify those values.
- Replace Farelogix `DOCS` free text wholesale, redact passenger titles with a schema-valid neutral
  sentinel, and replace document issuing-country, issue-date, and expiry-date values with typed
  sentinels.
- Include Travelport state/province leaves in address redaction.
- Expand golden assertions so planted plaintext, not only rewrite counts, proves coverage.

Explicitly out of scope by product direction: required-rule anchors, BA/LA NDC rules, and Travelport
structured-name expansion beyond the existing first/last coverage.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `pii-rules`: the PII type vocabulary adds age and IP address, and baked Travelfusion, Farelogix,
  and Travelport address rules cover the identified plaintext surfaces.
- `travelfusion-pii-baseline`: booking-detail redaction encrypts phone leaves, traveller demographic
  values, sensitive custom parameters, and client IP values without required anchors.
