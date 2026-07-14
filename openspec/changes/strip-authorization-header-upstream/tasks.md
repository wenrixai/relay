# Tasks — strip the client Authorization header before forwarding upstream

## 1. Failing tests first (TDD)

- [ ] 1.1 `tests/unit/test_header_hygiene.py`: `clean_request_headers` drops `Authorization` (any case) → not present in the cleaned list.
- [ ] 1.2 `tests/integration` (forwarder): a request with `Authorization: Basic …` to a pass-through / non-swap channel → the header captured at `httpx.AsyncClient.request` carries no `Authorization`.
- [ ] 1.3 Regression: a Travelport (swap-enabled) channel → the upstream request DOES carry the handler-set `Authorization: Basic <channel creds>` (swap runs after hygiene), and it is NOT the client's value.

## 2. Implementation

- [ ] 2.1 Add `"authorization"` to the request-path drop condition in `_drop_request` (header_hygiene.py). Confirm credential-swap header injection (forwarder `_request_header_swap`) runs AFTER `clean_request_headers`, so Travelport still works.

## 3. Docs

- [ ] 3.1 Add `Authorization` to the documented strip list in `docs/PROJECT.md` §9.1.

## 4. Verify

- [ ] 4.1 Targeted suites green.
- [ ] 4.2 `just ci` green (lint + fmt + types + pylint + full test + coverage).
