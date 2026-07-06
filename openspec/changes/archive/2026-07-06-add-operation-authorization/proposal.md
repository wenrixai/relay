## Why

`ChannelConfig.authorization.allowed_operations` is fully modeled and hung off every channel, but it
is **enforced nowhere** — the forwarder never checks it, and it is only counted in the admin
diagnostics snapshot. An operator who restricts a channel to a set of operations gets no protection:
every operation is forwarded. This is a silent security gap.

## What Changes

- Enforce the operation-**name** allow-list in the request pipeline. When a channel's
  `authorization.allowed_operations` is non-empty, the relay SHALL parse the operation name from the
  request body (via the channel handler's `parse_operation`) and reject any operation not on the list
  with **HTTP 403** `operation_not_allowed`, before any credential injection or upstream call.
- An empty `allowed_operations` list preserves the existing allow-all semantics (no parsing, no cost).
- Fail closed: if a list is configured but the operation cannot be determined (non-XML body, or a
  body that does not parse), the request is rejected 403 — an unverifiable operation is not allowed.
- New error shape: `forbidden_operation_response` → 403 JSON `{error:"forbidden",
  reason:"operation_not_allowed", detail, trace_id}` + `X-Wenrix-Error: operation_not_allowed`.
- New metric `channel_relay_operations_denied_total{channel}`.
- `requires_inspection` includes channels with `allowed_operations`, so the inspectable-body size cap
  (413) applies uniformly.

### Deferred (not in this change)

`AllowedOperation.version` (a semver-match expression) is **retained in config but not evaluated**.
No operation version is derived from the body today and there is no semver comparator; version-range
matching is deferred to a follow-up change. Enforcement here is operation-name membership only.

## Capabilities

### New Capabilities
- `operation-authorization`: the relay enforces a per-channel operation-name allow-list, failing
  closed with 403 for disallowed or undeterminable operations.

### Modified Capabilities
- `error-contract`: adds a 403 `operation_not_allowed` response shape (JSON, `X-Wenrix-Error`,
  echoes `x-wenrix-trace-id`, omits `Server`, PII-free `detail`).

## Impact

- `src/channel_relay/proxy/errors.py`: `ErrorReason.OPERATION_NOT_ALLOWED` +
  `forbidden_operation_response(trace_id)`.
- `src/channel_relay/proxy/forwarder.py`: new `_authorization_stage` invoked after the handler is
  resolved and before credential injection; reuses `parse_bytes` + `handler.parse_operation`.
- `src/channel_relay/middleware/content.py`: `requires_inspection` also true when
  `allowed_operations` is configured.
- `src/channel_relay/observability/metrics.py`: `record_operation_denied` +
  `operations_denied_total` in totals/snapshot.
- Tests: new `tests/unit/test_operation_authorization.py` and forwarder integration coverage.
