# Tasks — scope response credential cleanup to the security/session subtree

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_channel_credential_swap.py`: Amadeus/Sabre response with a business element named `SessionId`/`SecurityToken`/`BinarySecurityToken` OUTSIDE the `Security` header → left unchanged; the real auth field inside `Security` → encrypted.
- [ ] 1.2 Travelport response with a `SessionKey` attribute outside the session region → unchanged; the session-region `SessionKey` → encrypted.
- [ ] 1.3 Travelfusion response with a `LoginId`/`XmlLoginId` outside the login/session region → unchanged; the login-region field → stripped.
- [ ] 1.4 Regression: existing golden response fixtures still redact/strip the genuine fields.

## 2. Implementation

- [ ] 2.1 Add a helper to resolve the security/session region per handler (SOAP `Security` header; Amadeus session block; Travelport session subtree; Travelfusion login region).
- [ ] 2.2 Change the three `swap_response` methods to iterate within that region instead of `root.iter("*")`.

## 3. Verify

- [ ] 3.1 Targeted suites green.
- [ ] 3.2 `openspec validate scope-response-credential-cleanup --strict`.
- [ ] 3.3 `just ci` green.
