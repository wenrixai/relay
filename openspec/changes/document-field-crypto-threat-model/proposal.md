# Document the field-crypto threat model: CTR integrity and IV-collision bounds

## Why

Two properties of the default (random-IV CTR) token mode are real, accepted design choices, but the
spec states them too lightly to be operationally safe — and the code has no guardrail keyed to them.

1. **The default CTR mode has no integrity protection.** `codec.decrypt` detects corruption on the
   CTR path only incidentally — via `UnicodeDecodeError` or an optional smaz `ValueError`. A single
   bit-flip inside an ASCII PII value (a name, PNR, date) frequently still decodes as valid UTF-8 and
   passes silently. Since `ENC_` tokens round-trip through the client (issued in a response, replayed
   in a later request for de-anonymization), an actor who can capture and resubmit a token can flip
   targeted ciphertext bits and alter the decrypted value forwarded to the channel, with no detection.
   The deterministic/SIV mode *is* authenticated; the two modes differ materially in tamper-resistance.
   This is "confidentiality-only in v1" per D1 — but the spec should say plainly that the default mode
   provides no integrity, so the accepted risk (and the AEAD upgrade path via the reserved control
   bits) is explicit rather than implied.

2. **96-bit random IV has a birthday bound with no volume-based rotation policy.** `os.urandom(12)`
   per encryption gives the standard ~2⁴⁸ birthday bound; a CTR nonce collision under a fixed epoch
   key leaks the XOR of the colliding plaintexts. Epoch rotation is manual/calendar-driven today, with
   no guidance tying rotation to encryption **volume**, so a long-lived high-throughput epoch could
   approach the bound.

## What Changes

- `token-codec` (Token format) SHALL state explicitly that the default random-IV CTR mode is
  confidentiality-only and provides **no integrity/tamper protection** (only the deterministic SIV
  mode is authenticated), and that an authenticated default mode may be introduced later via the
  reserved control bits without breaking the format.
- `crypto-keyring` (Active epoch selection) SHALL require documented **volume-based** epoch-rotation
  guidance (rotate before an epoch approaches the safe encryption-count bound), not only
  calendar-based rotation.

No behavioral code change is required for v1; this pins the threat model and rotation policy. (A
follow-up MAY add an AEAD default mode.)

## Capabilities

### Modified Capabilities
- `token-codec`: the default mode's lack of integrity is stated explicitly as an accepted, versioned
  v1 property.
- `crypto-keyring`: epoch rotation guidance is volume-aware.

## Impact

- `openspec/specs` deltas (this change) + `SECURITY.md` / `docs/`: record the confidentiality-only /
  no-integrity property and the volume-based rotation guidance.
- No `src/` behavior change in v1; a later AEAD-default change is tracked separately.
