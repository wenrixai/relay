# Cover mixed-content tail text in redaction and de-anonymization

## Why

Two fail-open edges in `pii/engine.py`, both silent (no error, no metric):

1. **`element.tail` is never scanned.** `deanonymize_request_body` iterates `element.text` and
   `element.attrib` only; `_redact_reference_rule` likewise reads `node.text`. lxml puts text that
   follows a child element into that child's `.tail`. An `ENC_` token or a PII value living in
   mixed-content tail (e.g. `<a/>ENC_xxx<b/>`) is silently skipped: on the request path the token is
   forwarded to the channel still encrypted (violating "the channel always receives plaintext"); on
   the response path matching PII in tail text is never redacted. Neither raises nor increments a
   metric — a quiet fail-open against the "never forward partially processed PII" contract.

2. **`assert ctx.keyring is not None` is the only crypto guard** before `encrypt()` on the
   non-`force_redact` path (`engine.py:131`, `:299`). `assert` is stripped under `python -O` /
   `PYTHONOPTIMIZE`; the guard vanishes and control falls into `encrypt(value, None, …)`, which fails
   only incidentally via an unrelated `AttributeError` caught by the broad outer `except`. Fail-closed
   today holds only by accident, not by contract.

## What Changes

- Redaction (reference rules) and de-anonymization SHALL also process `element.tail` text, applying
  the same token/value matching used for `element.text`, so mixed-content tail is covered in both
  directions and the same failure semantics (whole-value vs embedded) apply.
- Replace the `assert ctx.keyring is not None` guards with explicit `if … raise RedactionError(...)`
  so fail-closed behavior is guaranteed under optimized interpreters.

## Capabilities

### Modified Capabilities
- `redaction-engine`: response redaction and request de-anonymization cover mixed-content tail text;
  the keyring guard is explicit (not assert-based).

## Impact

- `src/channel_relay/pii/engine.py`: scan `.tail` in `deanonymize_request_body` and
  `_redact_reference_rule` (and field-rule tail where applicable); replace asserts with explicit
  raises.
- `tests/unit/test_pii_engine.py`: tail-text round-trip (request) and tail-text reference redaction
  (response); a fail-closed test that does not rely on `assert` being active.
