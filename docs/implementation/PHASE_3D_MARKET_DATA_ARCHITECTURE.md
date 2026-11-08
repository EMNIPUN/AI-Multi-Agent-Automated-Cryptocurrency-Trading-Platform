# Phase 3D — Public Bybit Market Data Architecture

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Scope | Local Windows personal-use dashboard |
| Private Bybit / orders / bindings / Auth E2E | **Out of scope** |

---

## Goal

Stream and display **Bybit V5 public** market data (tickers, confirmed klines, order book, recent trades) for BTCUSDT / ETHUSDT / SOLUSDT (configurable), on spot and USDT perpetual categories, without private credentials.

---

## Reused vs new

| Existing | Role |
|----------|------|
| `lightweight-charts` + prior `CandleChart` | Charting library reused; markets page uses `MarketCandleChart` |
| `agent/market_data.py` EMA/RSI | Logic mirrored in API + TS (no look-ahead) |
| `bot/market.py` | Manual CLI only — not duplicated into HTTP |
| Auth / binding / wallet routers | Untouched; kill switches remain off |

| New | Role |
|-----|------|
| `apps/api/app/market_data/*` | Public REST client, candle series, order-book sync, WS protocol/manager, FastAPI router |
| `apps/web/src/lib/market/*` | Types, indicators, candle/orderbook helpers, API client |
| `apps/web/src/app/api/market/*` | Unauthenticated allowlisted Next → FastAPI proxy |
| `/markets` + dashboard `PublicTickerStrip` | Live public UI |

---

## Data paths (must stay distinct)

| Path | Meaning |
|------|---------|
| `public_live` | Real Bybit public REST (no API keys) |
| `public_simulated` | Injected fake transport (tests / `MARKET_DATA_SIMULATED`) |
| `sample` / fixture | Offline SAMPLE charts (agent observability) |
| Private wallet / bindings | Separate — still gated; **not** implied by public LIVE |

Stale WS / unsynced books are labeled **STALE** and must not be treated as live authority.

---

## Backend surface

- `GET /api/v1/market/meta`
- `GET /api/v1/market/status`
- `GET /api/v1/market/tickers`
- `GET /api/v1/market/klines` (forming bar excluded; EMA20/50/200 + RSI14)
- `GET /api/v1/market/orderbook`
- `GET /api/v1/market/trades`

No auth required. No private endpoints. No order submission.

WebSocket manager (`PublicMarketWsManager`) provides resilient connect/reconnect, heartbeat, subscription restore, schema validation, snapshot/delta book sync, and bounded trade buffers. REST polling powers the UI in this increment; the manager is covered by deterministic unit tests and is ready for process-level attach without private streams.

---

## Frontend

- `/markets`: category (spot / USDT perpetual), symbol, timeframe (1m–1D), live candle + volume + EMAs, RSI, watchlist 24h change, order book spread, recent trades, connection badge
- `/dashboard`: `PublicTickerStrip` (public quotes only)
- Next proxies under `/api/market/*` (allowlist only)

---

## Local startup

```powershell
# Terminal 1 — FastAPI (loopback)
.\.venv\Scripts\python.exe -m uvicorn apps.api.app.factory:create_app --factory --host 127.0.0.1 --port 8000

# Terminal 2 — Next.js
cd apps\web
npm run dev
```

Open `http://localhost:3000/markets`. Public REST calls go Next → FastAPI → `https://api.bybit.com/v5/market/*`.

Optional: `MARKET_DATA_SIMULATED=true` forces fake transport (no outbound Bybit).

---

## Kill switches (unchanged)

- `EXCHANGE_BINDING_PERSISTENCE_ENABLED=false`
- `EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED=false`
- `PRIVATE_DATA_READS_ENABLED=false`
- `AGENT_ALLOW_LIVE=false`
- `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false`
