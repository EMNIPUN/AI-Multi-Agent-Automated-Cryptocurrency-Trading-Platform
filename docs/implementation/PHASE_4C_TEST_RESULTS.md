# Phase 4C — Test Results

## Python

```text
pytest tests/test_phase4a_multi_agent_signals.py \
       tests/test_phase4b_signal_history.py \
       tests/test_phase4c_auto_signal_engine.py -q
40 passed
```

Phase 4C cases cover:

1. Confirmed candle → one evaluation  
2. Forming candle → no evaluate  
3. Duplicate event suppression  
4. Out-of-order candle handling  
5. WS confirm enqueue (forming ignored)  
6. Missing candle backfill enqueue  
7. Restart checkpoint recovery  
8. Concurrent scheduler prevention  
9. SQLite write failure → BLOCKED  
10. Atomic signal/risk persistence  
11. Corrupted risk fail-closed  
12. Daily halt survival  
13. Stale market-data rejection  
14. Strategy version isolation  
15. No private exchange / no orders in status APIs  
16. Schema migration v2 safety  

## Frontend

```text
npm run typecheck → pass
npm run lint      → 0 issues
npm test          → 32 passed
npm run build     → exit 0
  (includes /api/signals/engine/status|start|stop)
```
