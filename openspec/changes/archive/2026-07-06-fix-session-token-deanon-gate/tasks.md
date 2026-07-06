## 1. Failing test

- [x] 1.1 `tests/integration/test_session_deanon_gate.py`: a credentialed Amadeus channel with
      `pii=ChannelPII(enabled=False)` — first response's `awsse:Session` fields are `ENC_`; a
      follow-up request replaying those `ENC_` tokens (in `awsse:Session`, outside the swapped
      `Security`) is de-anonymized so **no `ENC_` reaches the channel**. (Amadeus, not Sabre: Sabre's
      token lives inside the wholesale-swapped `Security` element, so it is discarded either way and
      would not isolate this bug.)

## 2. Forwarder gate

- [x] 2.1 `src/channel_relay/proxy/forwarder.py`: add
      `need_session_deanon = handler.requires_response_keyring(channel) and keyring is not None and
      kind is ContentKind.XML`
- [x] 2.2 Enter the request body block on `need_deanon or need_cred_body`; run `_request_pii_stage`
      on `need_deanon` (= `need_pii or need_session_deanon`)

## 3. Verification

- [x] 3.1 Existing `test_pii_sabre_relay.py` / `test_pii_amadeus_e2e.py` (pii.enabled=True) still
      green — no regression
- [x] 3.2 `just test-fast` green
- [x] 3.3 `just ci` green — 346 passed, 95% coverage
