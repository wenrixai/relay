## 1. Error shape

- [x] 1.1 `tests/unit/test_errors.py`: `forbidden_operation_response(trace_id)` returns 403 JSON with
      `reason=operation_not_allowed`, `X-Wenrix-Error: operation_not_allowed`, media type JSON
- [x] 1.2 `src/channel_relay/proxy/errors.py`: add `ErrorReason.OPERATION_NOT_ALLOWED` and
      `forbidden_operation_response(trace_id)`

## 2. Metric

- [x] 2.1 `src/channel_relay/observability/metrics.py`: `record_operation_denied(channel)` +
      `operations_denied_total` counter and snapshot entry (admin snapshot test updated)

## 3. Inspection gate

- [x] 3.1 `src/channel_relay/middleware/content.py`: `requires_inspection` true when
      `channel.authorization.allowed_operations` is non-empty
- [x] 3.2 `tests/unit/test_content.py` green (existing suite covers requires_inspection)

## 4. Enforcement stage

- [x] 4.1 `tests/unit/test_operation_authorization.py`: allowed op forwarded; disallowed op → 403 and
      upstream `MockTransport` **never invoked**; empty list allows all; non-XML body with a
      configured list → 403
- [x] 4.2 `src/channel_relay/proxy/forwarder.py`: `_authorization_stage(...)` returning
      `Response | None`; called after `handler = get_handler(...)` and before the credential header
      swap; skipped when the list is empty
- [x] 4.3 Parse failures mapped like the other body stages (oversize→413, XmlOpsError→502
      `xml_parse_error`); disallowed / undeterminable op → 403 + `record_operation_denied`

## 5. Verification

- [x] 5.1 `just test-fast` green
- [x] 5.2 `just ci` green — 351 passed, 95% coverage
