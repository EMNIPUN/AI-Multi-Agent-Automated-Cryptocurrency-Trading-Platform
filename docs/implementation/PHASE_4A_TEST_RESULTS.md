# Phase 4A — Test Results

Date: 2026-11-07 (local Windows)

## Python

```text
pytest tests/test_phase4a_multi_agent_signals.py -q
15 passed
```

Covered:

1. Bullish trend evaluation  
2. Bearish trend bias  
3. Sideways / non-strong-BUY  
4. Conflicting / mixed series  
5. Stale data → BLOCKED  
6. Missing candles  
7. Duplicate signal suppression  
8. Incorrect market category  
9. Volatility risk veto path  
10. Stop-loss / TP hypothetical sizing  
11. Daily hypothetical loss halt  
12. Replay determinism  
13. Spot vs linear isolation  
14. API status + fixture evaluate (`execution_allowed=false`, `private_api_used=false`)  
15. Unknown symbol allowlist block  

## Frontend

```text
npm run typecheck  → pass
npm run lint       → 0 warnings/errors
npm test           → 31 passed (includes signals proxy allowlist)
npm run build      → exit 0 (includes /api/signals/* routes)
```

## Security assertions in tests

- `PRIVATE_DATA_READS_ENABLED=false`
- `AGENT_ALLOW_LIVE=false` reflected on `/api/v1/signals/status`
- Root `trading_endpoints: false`
- Decision payloads include `not_an_order: true`
- Proxy allowlist rejects wallet/orders paths
