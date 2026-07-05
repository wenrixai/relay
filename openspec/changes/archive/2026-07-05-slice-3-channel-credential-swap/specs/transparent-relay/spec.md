## MODIFIED Requirements

### Requirement: Content handling and pass-through

The relay SHALL pass through non-XML/unknown content transparently, support chunked transfer, pass
compressed bodies through untouched when no inspection is required, and reject bodies exceeding the
inspectable-size cap with 413 when inspection is required. Inspection is required when PII is enabled
or when configured channel credentials require body parsing for operation parsing, request swap, or
response cleanup/encryption.

#### Scenario: Credential swap requires inspection
- **WHEN** a channel has credentials that require XML credential swap
- **THEN** oversized inspectable request bodies are rejected with 413 before forwarding
