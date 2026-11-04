# Phase 1D — Confirmed Candles & Signal Checkpoint (Bybit-only)

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Market data source | **Bybit V5 only** (`session.get_kline` via `fetch_candles`) |
| Explicitly excluded | TradingView MCP, Apify Actors, other MCP market feeds |
| Constraints | Offline pytest only; no Bybit network; no trading CLIs; no commit/push |
| Related | Phase 1A / 1B / 1C reports |

---

## Root cause (pre-1D)

Bybit REST klines include a **still-forming** newest candle. The EMA/RSI strategy previously indexed `closes[-1]`, so unfinished bars could produce actionable crosses that flip within the same interval. Repeated polling (and restarts) could also re-emit the same closed-bar decision without a durable checkpoint.

**Policy:** never assume a newly fetched REST candle is closed.

---

## Implementation summary

### Pipeline

```text
Bybit get_kline (existing helper)
  → normalize / sort oldest→newest
  → filter_confirmed_candles(now_utc, grace, skew, staleness, min_bars)
  → EmaRsiStrategy.evaluate(confirmed only)
  → signal_id checkpoint (BUY/SELL)
  → Phase 1A position / 1C risk / 1B intent gates
  → execute (dry-run default) + mark ledger if successful
```

### Files (Bybit-only agent path)

| File | Role |
|------|------|
| `agent/market_data.py` | `fetch_candles` — documents forming-bar risk |
| `agent/candle_time.py` | UTC ms normalize; interval close for `1..720`, `D`, `W`, `M` |
| `agent/confirmed_candles.py` | Pure closed-bar filter (no I/O) |
| `agent/signal_ids.py` | Stable id: strategy/version + symbol + category + interval + close_ms + config + action |
| `agent/signal_ledger.py` | SQLite checkpoint `data/signal_ledger.sqlite3` |
| `agent/strategies/ema_rsi.py` | Confirmed bars only; formulas/thresholds unchanged |
| `agent/runner.py` | Wires filter → dedupe → plan/execute |
| `agent/config.py` | `AGENT_CANDLE_GRACE_MS` (default 2000), skew, optional staleness |

No TradingView/Apify imports under `agent/`.

---

## Confirmed-bar rules

A candle is confirmed only when:

```text
now_utc_ms >= candle_close_ms(start, interval) + grace_ms
```

- **Clock:** `datetime.now(timezone.utc)` in the runner (injectable `now_ms` in tests).
- **Grace / safety margin:** default **2000 ms** (`AGENT_CANDLE_GRACE_MS`).
- **Skew:** reject candle starts too far in the future (`AGENT_MAX_CLOCK_SKEW_MS`, default 5000).
- **Stale / malformed / duplicate / unsupported interval / insufficient warmup:** `CandleFilterReject` → journal block → **no new entries**.

Warmup: `max(ema_slow+2, rsi_period+2)` **confirmed** bars.

---

## Signal checkpoint / dedupe

Actionable `signal_id` keys:

- strategy id + version (`ema_rsi` / `1`)
- symbol, category, interval
- confirmed bar **close** time (ms)
- indicator config hash
- action (`BUY` / `SELL`)

**HOLD** is not checkpointed (not an entry intention).

After successful `execute` (including dry-run intent record), the id is persisted. Restart + repeated polls skip the same id (`idempotent_skip`). Correlation id for Phase 1B intents is derived from `signal_id`.

---

## Preserved safety (1A / 1B / 1C)

| Control | Status |
|---------|--------|
| 1A UNKNOWN position blocks new exposure | Intact |
| 1B durable `orderLinkId` / no blind retry | Intact |
| 1C persistent risk halt / recovery_required | Intact |
| `AGENT_DRY_RUN` default `true` | Verified this run |
| `AGENT_ALLOW_LIVE` default `false` | Verified this run |

---

## Offline verification

```powershell
.\.venv\Scripts\python.exe -c "from agent.config import load_settings; s=load_settings(); print(s.dry_run, s.allow_live)"
.\.venv\Scripts\python.exe -m pytest tests -q --tb=line
```

| Check | Result |
|-------|--------|
| Defaults | `dry_run True`, `allow_live False` |
| Pytest | **80 passed** in ~3.27s |
| Bybit / trading CLIs | **Not contacted / not run** |
| TradingView / Apify | **Not used** |

Coverage includes: forming vs closed bars, grace boundary, chronological sort, duplicates, malformed OHLCV, warmup, stale data, unsupported intervals, D/W/M closes, ledger restart, repeated-poll dedupe, and 1A/1B/1C regression checks.

---

## Remaining limitations

1. Confirmation uses **local UTC + grace**, not Bybit server time — if the host clock is badly ahead, confirmation could be early (mitigated by grace/skew; still a residual risk).
2. Weekly/monthly close conventions follow documented UTC calendar math; edge cases vs Bybit’s exact bar opens should be spot-checked in a later dry-run soak (not done here).
3. Manual CLI market views are unchanged and may still show forming bars.
4. Fill promotion `ACCEPTED → FILLED` remains a later milestone.

---

## Suggested next milestone (1E)

Evidence-based intent fill reconciliation and/or read-only API status endpoints — still Bybit-primary; no TradingView dependency required.

---

## Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Forming bars never generate actionable entries | **Pass** |
| Closed bars validated deterministically (UTC + grace) | **Pass** |
| Repeated ticks/restarts do not duplicate entry intents | **Pass** |
| Uncertain/stale/malformed data blocks new entries | **Pass** |
| 1A/1B/1C intact; dry-run / allow_live defaults unchanged | **Pass** |
| Full offline suite passes; no exchange activity | **Pass** (80) |
| No TradingView / Apify integration | **Pass** |

---

*End of Phase 1D confirmed-candles report.*
