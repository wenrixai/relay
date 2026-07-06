# Security Policy

This document describes the security posture of Wenrix Channel Relay v2, how to report
vulnerabilities, which versions receive fixes, how secrets are handled, and the threat
model the relay is designed against.

For the broader security design and rationale see the security section of `PROJECT.md`.
For engineering process, review requirements, and how to land a security fix see
`CONTRIBUTING.md`.

## Reporting a Vulnerability

We practice coordinated vulnerability disclosure.

- Report privately to **security@wenrix.com**.
- Do **not** open public GitHub issues, pull requests, or discussions for security
  vulnerabilities. Public disclosure before a fix is available puts users at risk.
- Include enough detail to reproduce: affected version, configuration, request/response
  samples (with any real PII removed), and the observed versus expected behavior.

### What to expect

- **Acknowledgement**: we aim to acknowledge your report within **3 business days**.
- **Coordinated disclosure**: we work with reporters toward a coordinated disclosure of
  up to **90 days** from the acknowledgement date. If a fix ships sooner, disclosure can
  happen sooner by mutual agreement. If more time is genuinely required, we will
  communicate the reason and a revised timeline.
- We will keep you informed of remediation progress and credit reporters who wish to be
  credited once a fix is released.

## Supported Versions

Security fixes follow semantic versioning. We support the **current minor** release and
**one prior minor** release. Older minors do not receive security fixes; upgrade to a
supported line.

| Version         | Supported          |
| --------------- | ------------------ |
| Current minor   | Yes                |
| One minor prior | Yes                |
| Older minors    | No                 |

For example, if the current release line is `2.4.x`, then `2.4.x` and `2.3.x` receive
security fixes, while `2.2.x` and earlier do not.

## Secret Handling

The relay handles several classes of secrets. None of them are logged, and none are
committed to the repository.

### PII master key

- Stored in a **Kubernetes Secret**, provisioned **create-if-absent**. The key is
  generated once if it does not already exist and is **never regenerated on `helm
  upgrade`**.
- **Never logged** and **never committed** to the repository.
- Used to HKDF-derive the per-epoch encryption keys that protect traveler PII (see the
  threat model below). Rotation is handled through the **1-byte key epoch** in the
  keyring: a new epoch is added, new data is encrypted under the new epoch, and existing
  tokens remain decryptable under their original epoch until retired.
- Provisioning and step-by-step epoch rotation for the Helm deployment are documented in
  `deployment/helm/chart/README.md` (create-if-absent Secret, `lookup` guard, mounted at
  `RELAY_PII_KEYRING_FILE`).

### Basic-auth credentials

- Channel-facing and client-facing basic-auth credentials are supplied at runtime as
  secrets, never logged, and never committed.

### mTLS certificates

- The **Wenrix public certificate** is baked into the image so the relay can present and
  validate the expected identity.
- The **Wenrix private key is never present in the relay**. The relay never holds
  material that would let it impersonate the Wenrix client.

## Threat Model Summary

Wenrix Channel Relay v2 is a **confidentiality-only** design (v1 of the security model).
Transport integrity is provided by TLS; the relay does not add cryptographic integrity to
individual PII fields.

### Assets

- **Traveler PII** carried in relayed XML.
- **Channel credentials** for the connected travel channels (Amadeus, Sabre, Travelport,
  BA/LA NDC, Farelogix AA/LH/UA, Travelfusion).

### Adversaries

- **Honest-but-curious Wenrix platform**: a party that operates the surrounding platform
  and may observe relayed content but does not actively attack it.
- **Passive observers**: parties that can read the relayed XML in transit or at rest in
  intermediate systems.

### Controls

- **Field confidentiality**: PII fields are encrypted with **AES-256-CTR** into
  self-describing `ENC_<base64url(control byte || 96-bit IV || ciphertext)>` tokens.
  Plaintext is smaz-compressed before encryption. Keys are HKDF-derived and selected by a
  1-byte key epoch.
- **Transport integrity**: provided by **TLS**.
- **Credential swapping and transparency**: channel credentials are swapped
  **structurally** (via lxml, never find-and-replace), and relay-specific headers are
  stripped so the relay stays transparent to both ends.
- **No persistent customer data storage**: the relay does not persist traveler PII or
  channel payloads.

### Explicitly out of scope for v1

- **Active token tampering** and **cryptographic integrity of individual fields**. The v1
  threat model assumes an honest-but-curious platform and passive observers, not an active
  attacker modifying encrypted tokens in flight. AES-256-CTR provides confidentiality, not
  authentication; per-field integrity is not a v1 guarantee and must not be relied upon.

## Related Documents

- `PROJECT.md` (security section): full security design and rationale.
- `CONTRIBUTING.md`: engineering process, required checks, and code review for landing
  security changes.
