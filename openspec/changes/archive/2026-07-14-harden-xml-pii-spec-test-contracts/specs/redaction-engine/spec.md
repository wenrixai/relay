## MODIFIED Requirements

### Requirement: Response redaction

For channels with `pii.enabled: true`, the relay SHALL redact XML/SOAP channel responses before
returning them to the client. Field rules select values by XPath, collect plaintext before rewriting,
and apply their configured action. Reference rules then replace occurrences of collected values in
their XPath-selected targets. The relay SHALL re-serialize once, preserving structure, namespaces,
and declarations. Channels without PII enabled SHALL pass through untouched. Unsupported inspected
content follows the `transparent-relay` fail-closed contract; rules cannot request a non-XPath path.

#### Scenario: Travelfusion wrapper operation parsed by handler
- **WHEN** a PII-enabled Travelfusion route returns `<CommandList><GetBookingDetails>...`
- **THEN** rule selection uses channel `travelfusion` and operation `GetBookingDetails`

#### Scenario: Travelfusion PII is reversible
- **WHEN** Travelfusion PII rules match passenger, contact, billing, address, or payment fields
- **THEN** every matched value is replaced with an `ENC_` token and decrypts back to the original value

#### Scenario: Golden redaction
- **WHEN** a PII-enabled channel returns an XML fixture with rule-matched fields
- **THEN** those fields are replaced per action and encrypted values decrypt to the originals

#### Scenario: Free-text reference redaction after collection
- **WHEN** a field rule collects person values and a reference rule targets free text containing them
- **THEN** the references and structured fields are redacted in the same pass

#### Scenario: Ignored pattern skipped
- **WHEN** a located node's text matches an `ignored_content_patterns` entry
- **THEN** that value is left unmodified

#### Scenario: Unknown namespace prefix is a no-match
- **WHEN** a rule XPath uses a namespace prefix absent from its declarations
- **THEN** the rule-path error counter increments, a safe warning is emitted, and processing
  continues unless the rule is required

#### Scenario: PII disabled passes through
- **WHEN** a channel without `pii.enabled` returns a response containing PII
- **THEN** the body is relayed byte-identical

#### Scenario: force_redact substitutes a fixed placeholder
- **WHEN** an encrypt rule matches on a channel with `pii.force_redact: true`
- **THEN** the value becomes the fixed `REDACTED` placeholder without consulting a keyring

#### Scenario: force_redact channel needs no keyring
- **WHEN** the only PII-enabled channel uses `pii.force_redact: true`
- **THEN** response redaction succeeds without `RELAY_PII_KEYRING`

### Requirement: Channel-aware operation parsing

The relay SHALL parse the operation from the body using the configured channel handler when channel
context is available. The generic fallback SHALL use the SOAP Body's first child local-name, or the
document root local-name for non-SOAP XML. Operations SHALL never be taken from client headers.

#### Scenario: SOAP operation parsed
- **WHEN** a SOAP request's Body contains `<ns:PNR_Retrieve>`
- **THEN** the parsed operation is `PNR_Retrieve`

#### Scenario: Handler parses wrapped operation
- **WHEN** a channel-specific handler recognizes an operation below a wrapper element
- **THEN** rule selection uses the handler-derived operation

#### Scenario: Header ignored
- **WHEN** a client supplies an operation-naming header contradicting the body
- **THEN** rule selection uses only the body-derived operation

## ADDED Requirements

### Requirement: Required rules prevent silent schema drift

For each selected field rule with `required: true`, the engine SHALL require at least one rewritten
value after XPath selection, ignored-pattern filtering, and extraction matching. An unsatisfied
required rule SHALL raise a redaction failure before any response is returned; the forwarder SHALL
map it to 502 `pii_redaction_failed` and SHALL return none of the upstream body.

#### Scenario: Required XPath no longer matches
- **WHEN** supplier schema drift renames or removes the node targeted by a selected required rule
- **THEN** the client receives 502 `pii_redaction_failed` and none of the upstream response body

### Requirement: XPath evaluation errors are observable and safe

The engine SHALL report every XPath evaluation error through an optional rule-path error callback
carrying only configured channel and rule ID. It SHALL emit a safe warning with the same identifiers
and SHALL NOT include payload values, XPath-selected content, tokens, credentials, or key material.
A non-required rule error SHALL remain a no-match and processing SHALL continue; a required rule
error SHALL subsequently fail because the rule is unsatisfied.

#### Scenario: Non-required XPath error continues
- **WHEN** a non-required rule XPath cannot be evaluated
- **THEN** the error is counted and warned, the rule rewrites nothing, and other rules continue

#### Scenario: Required XPath error fails closed
- **WHEN** a required rule XPath cannot be evaluated
- **THEN** the error is counted and the unsatisfied required rule fails the full redaction pass
