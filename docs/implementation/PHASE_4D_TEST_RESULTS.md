# Phase 4D — Test Results

## Scope honesty

Offline / gated unit tests only. **No claim of live Supabase E2E** until operator-approved cloud DDL + dual gates + authenticated run succeed.

## Python

```text
pytest tests/test_phase4d_supabase_signal_persistence.py \
       tests/test_phase4b_signal_history.py \
       tests/test_phase4c_auto_signal_engine.py -q
33 passed
```

Covered:

1. Cloud gates default OFF  
2. Repository write denial when gated  
3. Idempotent insert (offline session, gates bypassed for unit only)  
4. Cross-owner isolation  
5. Local outbox enqueue + sync drain no-op when gated  
6. SQLite import dry-run (no cloud write)  
7. API sync/status — no secrets, no orders  
8. Model owner + UTC fields  

Not yet (blocked on approval): live migration, live import, network interrupt against real Supabase.

## Frontend

Proxy allowlist includes `/api/v1/signals/sync/status`; Studio shows supabase writes-OFF + pending sync.
