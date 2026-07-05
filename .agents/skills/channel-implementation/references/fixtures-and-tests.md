# Fixtures, Sanitization, and Golden Tests

## Purpose

Real supplier payloads contain live PII and session credentials; the test suite needs their
exact XML shape. This file is the protocol for converting one into the other with zero leaks,
and the test patterns that turn sanitized fixtures into durable golden coverage.

## 1. Sanitization protocol

Targets live in `tests/fixtures/<channel>/`, one file per operation, named after the operation
(`get_reservation_response.xml`, `session_create_request.xml`).

Rules of substitution:

- **Value-only edits.** Structure, namespaces, element/attribute names, whitespace stay
  byte-identical — rules are validated against these shapes. Use a plain-text substitution
  script with per-value occurrence-count assertions; verify output still parses with lxml.
- **Shape-identical fakes.** Same charset/format/rough length (`WHITE`→`BROWN`,
  `9850242034`→`0000000000`, locator→`TESTAA`-style, GUIDs→zeroed GUIDs). Keep titles and
  suffixes (`ALON MS`→`DANA MS`, phone suffix `-C-1.1` kept).
- **Consistency.** Same real value → same fake everywhere, including free-text echoes,
  history mirrors, and e-ticket strings — reference-rule tests depend on the echo matching.
- **Replace every credential**, even in "response" files: session tokens
  (`BinarySecurityToken`), usernames/passwords, organization codes.
- **Distinct fakes across files** for values tests assert on (don't reuse `TESTBB` for two
  different real locators).
- **Truncate huge repetitive payloads** (sales reports with hundreds of records) to ~5 records
  plus one of each structural variant (e.g. the miscellaneous-charge document record) — tests
  stay fast, shapes stay covered.
- Keep non-PII verbatim: ticket/document numbers, amounts, dates (except date of birth),
  city/airline codes, agent sign-in codes, pseudo-city codes.
- Fan out sanitization to parallel subagents for multi-file payload sets; require each to
  return a real→fake replacement table (you need the fakes for test assertions) and a list of
  borderline values it kept.

Leak verification (mandatory, do it yourself — don't trust the sanitizer's own check):

```bash
grep -rEi "<name1>|<name2>|<token-fragment>|<card-last4>|..." tests/fixtures/<channel>/
# must exit 1 (zero hits)
```

Then delete or gitignore the raw payload directory before committing. Note: the
`end-of-file-fixer` pre-commit hook appends a trailing newline to fixtures — harmless, but the
first commit attempt will "fail" with modified files; just re-add and commit.

## 2. Golden unit tests (`tests/unit/test_pii_<channel>.py`)

Shared fixtures already exist in `tests/conftest.py` — use them, don't redefine:
`pii_keyring` (deterministic keyring), `baked_ruleset` (the shipped `rules_fallback.json`),
`xml_texts` (texts of elements by local-name), plus `FIXTURES_DIR`. Test subdirectories have no
`__init__.py`, so shared helpers go in conftest (importable everywhere), and unit/integration
file **basenames must be unique** or pytest collection fails (`test_pii_sabre.py` vs
`test_pii_sabre_relay.py`).

One test class per operation. Per class, cover:

1. **Operation parsing** — `parse_operation(parse_bytes(fixture)) == "<OperationRS>"`.
2. **Encrypt + round-trip** — redacted values full-match `TOKEN_RE`, `decrypt()` returns the
   planted fake, and `deanonymize_request_body` restores it (attributes included).
3. **Mask one-way** — planted value absent, node/attribute is all mask chars, never `ENC_`.
4. **Counts** — assert the `counts` dict (per-`pii_type` totals) so a silently dead XPath fails
   the suite (an XPath that stops matching is a no-match, not an error).
5. **Non-PII preservation** — locators, ticket numbers, amounts, agent codes asserted present
   verbatim.
6. **Uncovered operation** — an unknown operation redacts nothing and passes through.

Leak probes: prefer full-node probes (`b"<stl19:Number>0000000000<"`) over bare substrings —
zero-filled fakes collide with other zeroed values (GUIDs) and false-positive.

## 3. Relay integration tests (`tests/integration/test_pii_<channel>_relay.py`)

Mirror `tests/integration/test_pii_sabre_relay.py`: `httpx.MockTransport` serves the fixture
(never real network), channel configured with `pii.enabled=true` and real-shaped credentials,
`RELAY_RULES_API_URL` unset so the baked fallback loads. Assert:

- Response PII redacted end-to-end and supplier session token is an `ENC_` token (credential
  cleanup runs BEFORE redaction).
- Request credentials never reach the supplier (configured swap fragment present; client
  username/password absent from the forwarded body).
- A returned `ENC_` token sent on the next request is de-anonymized upstream (and, for SOAP
  channels, then replaced wholesale by the security-header swap).

## 4. Close-out gates

- `just ci` — lint, format, mypy strict, pylint, full suite; every test under the pytest
  timeout.
- Bumped `rules_version` covered by a test.
- Raw payloads gone from the working tree; leak grep run against `tests/fixtures/<channel>/`.
- Conventional commit; OpenSpec change archived.
