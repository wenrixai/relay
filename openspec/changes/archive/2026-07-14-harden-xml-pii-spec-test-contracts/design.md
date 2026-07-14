## Context

Body inspection is security-sensitive because it restores encrypted request PII, injects supplier
credentials, and removes or encrypts sensitive response fields. The current implementation has one
hardened structural parser, for XML, and gzip handling around inspected XML. Treating other formats
as future-capable creates silent-pass-through risks. Required rules are the existing mechanism for
turning supplier schema drift into a fail-closed response.

## Decisions

### XML/SOAP is the inspection boundary

Requests that do not need body inspection and responses that do not need structural cleanup or PII
redaction remain opaque pass-through. When configured behavior requires inspection, non-XML content
is rejected before sensitive processing: request-side rejection is `415 unsupported_content_type`;
response-side rejection is `502 unsupported_content_type` and none of the upstream body is returned.
Gzip-wrapped XML is supported. JSON, MTOM/multipart, deflate, and unknown formats are not inspected.

Operation authorization keeps its existing independent behavior in this change; reconciling its
status/reason contract is a separate concern.

### XPath is the only rule path type

The rule schema accepts only `xpath`. An unsupported `path_type` invalidates the entire external or
baked ruleset through normal strict validation. This removes the unsafe state where a rule loads but
is silently skipped.

### Required anchors protect PII-heavy operations

`amadeus.pnr.surname` is required for `PNR_Reply`.
`travelfusion.booking.traveller_name` is required for both `GetBookingDetails` and
`GetLatestBookingDetails`. A required rule that locates no rewritable value aborts the full response
redaction and maps to the established `502 pii_redaction_failed` contract. No partially processed
upstream body is returned.

### XPath evaluation errors are bounded diagnostics

Every rule XPath evaluation failure, including an undeclared namespace prefix, increments
`channel_relay_pii_rule_path_errors_total{channel,rule_id}` and a matching in-process total exposed
as `statistics.pii_rule_path_errors_total` by `/admin/flare`. The only labels are configured channel
and rule ID, both drawn from bounded configuration/ruleset data. A safe warning identifies those two
fields but never includes XPath input values, payload fragments, tokens, or credentials. Non-required
rules continue after reporting; required rules subsequently fail because they rewrote nothing.

### Performance runs prove their scenario before measuring it

CI executes the four scenarios for each 2KB, 32KB, and 256KB payload size and publishes uniquely
named non-gating artifacts. A preflight must prove pass-through, structural Travelfusion credential
swap, XML response redaction, and valid-token de-anonymization before k6 load begins. Fixed mock
latency remains part of the measurement contract.

### Network policy ownership

The Helm chart deliberately emits no NetworkPolicy because channel and telemetry destinations are
deployment-specific. Customers enforce ingress/egress through cluster or cloud controls. Existing
pod/container hardening requirements remain unchanged.

## Risks and Mitigations

- Existing external rules using `jsonpath` will fail ruleset validation. This is intentional and is
  documented as an unsupported capability instead of silently leaving data unredacted.
- Required anchors can reject a legitimate supplier variant. The selected anchors are stable
  passenger-name structures covered by sanitized fixtures; the rejection is safer than forwarding
  an unredacted PII-heavy response.
- Rule IDs are externally supplied and could increase metric cardinality. Rulesets are bounded and
  loaded once; metrics use only the finite active rule IDs and configured channel names.
