# CryptoNova 72 — Signal Owner Fix

## Relationship

Supabase Auth user id, signal owner, and API session are the same UUID when a request is authenticated. Unattended signal persistence does not invent that id. It accepts only `SIGNAL_CLOUD_OWNER_USER_ID` after the operator copies it from a verified Auth user. `CRYPTONOVA_TEST_OWNER_USER_ID` is a test override, not a production owner.

If neither value is a UUID and source-of-truth mode is on, `resolve_sot_owner_user_id` raises. `get_signal_store` now turns that into HTTP 409:

```json
{"code":"signal_owner_unconfigured","execution_allowed":false}
```

No row is written. The store is not cached after the failure. Idempotency keys are unchanged because no insert occurs.

## Verification

- Unit test `test_signal_status_without_owner_is_conflict` returned 409.
- Live `GET /api/v1/signals/status` on `127.0.0.1:8200` returned 409 with `signal_owner_unconfigured` and `execution_allowed` false.
- `.env` does not have `SIGNAL_CLOUD_OWNER_USER_ID` set.

Restart recovery of signal rows was not run. There is no owner, and `signal_history` count is 0.

## Approval required

Supply the verified Supabase Auth user UUID for the development operator. It will be stored only in the gitignored environment as `SIGNAL_CLOUD_OWNER_USER_ID`. Do not send it in chat if the transcript is retained. After it is set, signal history reads, writes, and a process restart can be verified.
