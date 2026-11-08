# Phase 3D.1 — Public WebSocket Streaming Architecture

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Scope | Local Windows personal-use |
| Private Bybit / orders / wallet via stream | **None** |

---

## Pipeline

```
Bybit V5 public WS (spot | linear)
        ↓  allowlisted wss://stream.bybit.com/v5/public/{spot|linear}
PublicMarketWsManager (reconnect, heartbeat, validate, book sync)
        ↓  normalized events
MarketStreamHub (fan-out, bounded queues, backpressure)
        ↓  ws://127.0.0.1:8000/api/v1/market/stream
Browser /markets (useMarketStream) → incremental Lightweight Charts
        ↓  on WS failure
REST fallback (/api/market/*) labeled REST FALLBACK — never WS LIVE
```

---

## Reused

| Component | Role |
|-----------|------|
| `ws_manager.py` / `ws_protocol.py` / `orderbook.py` / `candles.py` / `indicators.py` | Core validation & sync |
| REST `/api/v1/market/*` | Snapshot seed + fallback |
| `MarketCandleChart` | Incremental updates (no full remount each tick) |

## New

| Component | Role |
|-----------|------|
| `real_ws.py` | Sync Bybit public socket; rejects non-allowlisted URLs |
| `stream_hub.py` | Process hub, client queues, category managers |
| `stream_endpoint.py` | FastAPI `/api/v1/market/stream` |
| `use-market-stream.ts` | Browser client + REST fallback |

---

## Browser protocol

- `{"op":"subscribe","category":"linear","symbols":["BTCUSDT"],"interval":"15"}`
- `{"op":"ping"}` → `{"op":"pong"}`
- Server events: `hello`, `subscribed`, `status`, `ticker`, `kline`, `orderbook`, `trade`, `orderbook_resync`, `error`
- **Forbidden:** any client field resembling upstream URL (`ws_url`, `upstream`, …)

Symbol allowlist: BTCUSDT/ETHUSDT/SOLUSDT (+ `MARKET_PUBLIC_SYMBOLS`).

---

## Security isolation

- Stream endpoint is public-data only; no Authorization required.
- Does **not** call wallet, bindings, or private Bybit APIs.
- Operator-local wallet proxy unchanged and separate (`/api/exchange/wallet`).
- Kill switches remain off for trading / binding persistence / private catalog reads.

---

## Local startup

```powershell
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
cd apps\web
npm run dev
```

Optional: `NEXT_PUBLIC_MARKET_WS_URL=ws://127.0.0.1:8000/api/v1/market/stream`

Open `http://localhost:3000/markets`.
