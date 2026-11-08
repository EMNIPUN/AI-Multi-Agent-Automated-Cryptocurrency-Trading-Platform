# Phase 3D.1 — Gate Summary

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Public WS end-to-end (local) | **PASS** |
| Live smoke (public Bybit → FastAPI stream) | **PASS** |
| Private / trading / bindings via stream | **NONE** |
| Operator-local wallet permissions | **Unchanged** |
| Cloud writes / migrations / git | **NONE** |

---

## Scoreboard

| Item | Result |
|------|--------|
| Bybit public WS bridge | **PASS** |
| FastAPI `/api/v1/market/stream` | **PASS** |
| Allowlist + no client upstream URLs | **PASS** |
| Hub backpressure / cleanup | **PASS** |
| Markets UI streaming + REST fallback labels | **PASS** |
| Incremental chart updates | **PASS** |
| Python tests | **22 passed** |
| Vitest | **29 passed** |
| TypeScript / ESLint | **PASS** / **PASS** |
| Production build | **BUILD=0** |
| Live smoke | **SMOKE=PASS** (`trade` + status events observed) |

---

## Kill switches retained

- `EXCHANGE_BINDING_PERSISTENCE_ENABLED=false`
- `EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED=false`
- `PRIVATE_DATA_READS_ENABLED=false`
- `AGENT_ALLOW_LIVE=false`

`OPERATOR_LOCAL_BROWSER_PROXY_ENABLED` remains a separate personal wallet path (not modified by this stream work beyond prior operator approval).

---

## Limitations

1. Order-book may emit `orderbook_resync` until a full snapshot is applied after gaps — UI refetches REST book.
2. One upstream manager per category (personal-use); symbol/interval unions restart the manager.
3. Browser connects directly to loopback FastAPI WS (not via Next proxy).
4. Auth E2E / private reads / live trading still out of scope.

---

## Startup

```powershell
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
cd apps\web
npm run dev
```

Open `http://localhost:3000/markets` — expect **WS LIVE** when stream is healthy; **REST FALLBACK** if not.
