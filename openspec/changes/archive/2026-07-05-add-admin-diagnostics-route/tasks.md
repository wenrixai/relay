## 1. Spec and tests
- [x] 1.1 Add OpenSpec delta for authenticated diagnostics behavior.
- [x] 1.2 Add unit tests for admin auth and redacted diagnostics payload.
- [x] 1.3 Add unit tests for in-process metric snapshots.

## 2. Implementation
- [x] 2.1 Add fail-closed admin Basic Auth dependency.
- [x] 2.2 Add diagnostics payload builder.
- [x] 2.3 Wire `GET /admin/flare` into the FastAPI app.
- [x] 2.4 Track metric counters in process for diagnostics snapshots.

## 3. Validation
- [x] 3.1 Run focused unit tests.
- [x] 3.2 Run OpenSpec validation.
- [x] 3.3 Run the repo's relevant checks.
