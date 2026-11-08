# Phase 4C — Automatic Closed-Candle Signal Architecture

## Scope

Signals-only automatic evaluation of **confirmed** public market candles.
**Not** automatic trading. No private Bybit calls. No order submission.

Engine version: `4C.1.0`  
Strategy scoring version (unchanged): `4B.1.0`

## Components

| Piece | Path |
|-------|------|
| Auto engine | `agent/multi_agent/auto_engine.py` |
| Atomic SQLite store + checkpoints + lock | `agent/multi_agent/signal_history_store.py` (schema v2) |
| Fail-closed pipeline | `agent/multi_agent/pipeline.py` |
| Process singleton | `apps/api/app/signals/engine_service.py` |
| HTTP controls | `GET/POST /api/v1/signals/engine/{status,start,stop}` |
| Studio UI | `SignalsPanel` auto-engine card |

## Flow

1. Operator starts engine (loopback POST) or sets `SIGNAL_AUTO_ENGINE_ENABLED=true`.
2. Engine acquires SQLite `scheduler_lock` lease (single-writer).
3. Public WS confirms enqueue jobs; REST poll/backfill fills gaps (bounded ≤3).
4. Worker fetches public klines → `filter_confirmed_candles` → `SignalPipeline.evaluate`.
5. Decision + paper risk persist **atomically**; checkpoint advances only after durable success.
6. Studio shows engine state, lag, last candle/signal, audit — distinct from trades.

## Idempotency key

`{strategy_version}|{category}|{symbol}|{interval}|{candle_close_ms}`

## Explicit non-goals

- Live order path / AgentRunner executor
- Private wallet reads for agents
- Supabase writes
- Profitability claims
