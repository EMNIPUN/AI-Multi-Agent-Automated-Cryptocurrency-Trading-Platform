# CryptoNova — Backtest Data Contract (Prompt 68A)

## Dataset identity

Every run records:

| Field | Meaning |
| --- | --- |
| `symbol` | e.g. `BTCUSDT` |
| `market_type` | `spot` (required for portfolio risk mode) or `linear` |
| `interval` | Bybit-style interval string (`15`, `60`, …) |
| `first_start_ms` / `last_start_ms` | Inclusive UTC ms open times |
| `candle_count` | Validated bar count |
| `content_hash` | SHA-256 over `start\|open\|high\|low\|close\|volume` lines |
| `provenance` | Fixture path, synthetic generator id, or caller tag |
| `source_kind` | `inline` \| `fixture_file` \| `bybit_public` (optional; not required for 68A) |

## Candle requirements

- Chronological, strictly increasing `start`
- Valid OHLC: `high ≥ max(open,close)`, `low ≤ min(open,close)`, finite numbers
- Volume ≥ 0 (zero volume allowed; **not** treated as a gap)
- No duplicate timestamps
- Missing intervals → warning (or hard reject if `allow_gaps=False`); **never forward-filled**
- Incomplete/forming bars must not be included in the offline series

## Fixture file schema

```json
{
  "meta": {
    "symbol": "BTCUSDT",
    "interval": "15",
    "market_type": "spot",
    "provenance": "…",
    "content_hash": "…",
    "label": "OFFLINE / SYNTHETIC OR HISTORICAL — NOT LIVE STREAM"
  },
  "candles": [
    {"start": 1700000000000, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 12.0}
  ]
}
```

## Replay clock

For bar `N` with interval `I` and grace `G`:

`now_ms = candle_close_ms(start_N, I) + G`

Default `G = 2000` ms (matches confirmed-candle grace policy).

## Isolation

Backtest journals use `bt68a_*.sqlite3` paths with `SUPABASE_SOT_ENABLED=false`. They must not target the operator paper journal filename.
