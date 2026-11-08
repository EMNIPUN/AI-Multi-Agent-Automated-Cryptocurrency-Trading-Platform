# Phase 3D — Test Results

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Real private Bybit / orders / cloud writes / git | **None** |

---

## Deterministic matrix

| # | Case | Result |
|---|------|--------|
| 1 | WebSocket connect/disconnect + subscribe ack | **PASS** |
| 2 | Reconnection backoff + subscription recovery / dedupe | **PASS** |
| 3 | Malformed WS messages | **PASS** |
| 4 | Duplicate / out-of-order candle updates | **PASS** |
| 5 | Order-book snapshot / delta sequencing | **PASS** |
| 6 | Stale market data not treated live | **PASS** |
| 7 | Indicator calculations (no look-ahead) | **PASS** |
| 8 | Spot / linear category separation | **PASS** |
| 9 | Component cleanup / bounded trade memory | **PASS** |
| 10 | Kill-switch isolation on `/market/status` | **PASS** |
| — | Forming kline exclusion + HTTP fake client routes | **PASS** |

Python suite: `tests/test_phase3d_market_data.py` → **13 passed** (`PYTEST=0`).

Frontend market Vitest: `src/lib/market/indicators.test.ts` → **4 passed**.

---

## Frontend quality gates

| Check | Result |
|-------|--------|
| Vitest (full) | **27 passed** (`VITEST=0`) |
| `tsc --noEmit` | **TSC=0** |
| ESLint | **LINT=0** |
| `npm run build` | **BUILD=0** |

---

## Real vs simulated

| Path | Used in tests | Used in local UI |
|------|---------------|------------------|
| Fake REST transport | Yes | Optional via `MARKET_DATA_SIMULATED` |
| Real Bybit public REST | No (unit) | Yes when FastAPI up |
| Private endpoints | Never | Never |
