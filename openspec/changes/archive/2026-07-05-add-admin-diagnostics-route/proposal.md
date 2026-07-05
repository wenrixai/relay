# Proposal: Admin Diagnostics Route

## Motivation
Operators need an authenticated support snapshot for debugging relay deployments without shelling into
the container or exposing secrets. The route should follow the Datadog flare idea: collect the useful
host, configuration, readiness, and statistics context in one safe payload.

## Approach
- Add `GET /admin/flare` as a JSON diagnostics snapshot.
- Reuse the configured Basic Auth credentials, but fail closed for this admin route when Basic Auth is
  disabled or credentials are incomplete.
- Include runtime, readiness, channel, and in-process metric details that are useful for proxy
  debugging.
- Redact sensitive material by construction: expose credential key names and configured booleans, never
  credential values, keyring material, auth secrets, request bodies, response bodies, or PII.

## Non-goals
- Downloadable archives or log bundles.
- HTML administration UI.
- Runtime config mutation.
