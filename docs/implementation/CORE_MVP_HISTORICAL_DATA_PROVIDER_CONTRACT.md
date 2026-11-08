# CryptoNova — Historical Data Provider Contract (68C)

| Field | Value |
| --- | --- |
| Milestone | Core MVP 68C |
| Module | `agent/backtest/history_provider.py` |
| Cache | `agent/backtest/dataset_cache.py` → `data/backtests/datasets/` |
| Network | Bybit **public** REST only (`/v5/market/kline`, `/v5/market/instruments-info`) |

---

## Scope

Load confirmed historical OHLCV for controlled backtests. Never synthesizes missing bars. Never uses private trading APIs or API keys.

## Supported controls (UI / run API)

| Control | Values |
| --- | --- |
| Symbols | `BTCUSDT`, `ETHUSDT`, `SOLUSDT` |
| Market types | `spot`, `linear` (linear = signal research data only) |
| Intervals | `15`, `60`, `240` |
| Time | UTC `start_ms` / `end_ms` |

Engine-supported intervals remain wider in 68A; the run API intentionally narrows the surface.

## Pagination

1. Request pages with `start`, `end`, `limit=1000`.
2. Reverse each page (Bybit returns newest-first).
3. Deduplicate identical overlapping boundary candles.
4. Reject conflicting duplicates (same `start`, different OHLCV).
5. Advance cursor to `last_start + 1`.
6. Drop bars that are not confirmed under `close_ms + grace_ms`.

## Integrity

- Invalid OHLC → hard reject.
- Empty confirmed series → hard reject.
- Gaps → validation warnings (no forward-fill).
- Dataset identity = SHA-256 of ordered OHLCV rows (`candle_content_hash`).

## Cache

- Path: `{results_dir}/datasets/{sha256}.json`
- Atomic write; symlink rejected on read.
- Meta must match expected symbol / interval / market_type when loaded for a run.
- Content hash recomputed on every load.

## Provenance labels

| Label | Meaning |
| --- | --- |
| `HISTORICAL BYBIT PUBLIC MARKET DATA` | Live public REST fetch (or verified cache of same) |
| `OFFLINE HISTORICAL FIXTURE` | Content-addressed local fixture |
| `SYNTHETIC TEST DATA` | Deterministic generator (68A demos) |

## Limitation

**Linear historical candles still use spot-like long-only simulation — not a leveraged Futures backtest.**
