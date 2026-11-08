# Phase 3D.1 — Test Results

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Private Bybit / orders / cloud / git | **None** |

---

## Deterministic matrix

| Case | Result |
|------|--------|
| Connect / subscribe / ping | **PASS** |
| Subscription recovery / cleanup on disconnect | **PASS** |
| Duplicate kline suppression | **PASS** |
| Order-book sync + sequence gap → resync | **PASS** |
| Stale / status emission | **PASS** (manager + UI modes) |
| Backpressure (bounded queue drop-oldest) | **PASS** |
| Spot / linear URL isolation | **PASS** |
| Upstream URL injection rejected | **PASS** |
| Symbol allowlist | **PASS** |
| No private flags on stream hello/meta | **PASS** |
| Indicator consistency (forming vs confirmed) | **PASS** (Vitest) |
| REST fallback labeling | **PASS** (UI mode `REST FALLBACK` ≠ WS LIVE) |

Python: `tests/test_phase3d1_websocket_stream.py` + `tests/test_phase3d_market_data.py` → **22 passed**.

Frontend Vitest → **29 passed**.

---

## Live public smoke (local)

| Check | Result |
|-------|--------|
| `ws://127.0.0.1:8000/api/v1/market/stream` | **Accepted** |
| Hello `private_reads_enabled` | **false** |
| Subscribe linear BTCUSDT | **subscribed** |
| Observed event types | `subscribed`, `status`, `orderbook_resync`, `trade` |
| Verdict | **SMOKE=PASS** (public-only) |

---

## Quality gates

| Gate | Result |
|------|--------|
| `tsc --noEmit` | **TSC=0** |
| ESLint | **LINT=0** |
| Vitest | **VITEST=0** (29) |
| `npm run build` | **BUILD=0** |
