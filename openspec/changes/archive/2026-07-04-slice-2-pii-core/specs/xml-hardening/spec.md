# xml-hardening Specification (delta)

## ADDED Requirements

### Requirement: Hardened parser factory
All XML parsing in the relay SHALL go through a single hardened lxml parser factory in
`pii/xml_ops.py` configured with `resolve_entities=False`, `no_network=True`, `load_dtd=False`,
`dtd_validation=False`, and a custom entity resolver that raises. Documents containing a DOCTYPE or
DTD SHALL be rejected. Direct `etree.fromstring`/ad-hoc parser construction outside the factory is
prohibited.

#### Scenario: XXE attempt rejected
- **WHEN** a document declares an external entity referencing a local file
- **THEN** parsing fails with a typed structural error and no file access occurs

#### Scenario: Billion-laughs rejected
- **WHEN** a document contains recursive entity expansion
- **THEN** parsing fails (DOCTYPE rejected) before expansion

#### Scenario: External DTD rejected
- **WHEN** a document references an external DTD
- **THEN** parsing fails and no network access occurs

### Requirement: Resource limits
The parser wrapper SHALL enforce a maximum document byte size (shared with the inspectable-body
cap), maximum element depth, and maximum node count. Exceeding the byte cap SHALL map to HTTP 413;
exceeding depth/node limits SHALL map to HTTP 502.

#### Scenario: Oversize document
- **WHEN** an inspectable body exceeds the configured byte cap
- **THEN** the relay responds 413

#### Scenario: Excessive depth
- **WHEN** a document nests elements beyond the depth limit
- **THEN** parsing fails with a structural error mapped to 502

### Requirement: Parse failure mapping
Malformed XML on a body the relay must inspect SHALL produce the 502 JSON error contract with
reason `xml_parse_error`; channels not requiring inspection are unaffected (pass-through). Every
hardening rejection SHALL increment `xml_parse_errors_total{channel, kind}`.

#### Scenario: Malformed body on PII-enabled channel
- **WHEN** a PII-enabled channel returns unparseable XML
- **THEN** the relay returns 502 JSON with reason `xml_parse_error` and the metric increments

#### Scenario: Pass-through channel unaffected
- **WHEN** a channel without PII/inspection receives malformed XML
- **THEN** the body is relayed untouched
