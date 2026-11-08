# CryptoNova — 69E Strategy Comparison

The three modes reuse one 68A result.

| Mode | What it adds | What it changes |
| --- | --- | --- |
| Technical baseline | Existing signals, risk, simulated fills, fees, equity | Nothing |
| News advisory shadow | Point-in-time revision context and conflict notes | Nothing in the trade |
| LLM advisory shadow | Previously recorded advice only | Nothing in the trade |

Both advisory modes display **Advisory Only — Trading Decisions Unchanged**. The simulation label is **Historical Simulation — Not Live Trading**.

Technical metrics are copied from the 68A analytics object: net realized PnL, drawdown, win rate, profit factor, expectancy, fees, and closed trades. News and LLM modes do not publish a second equity curve. A conflict or a disagreement is not a performance improvement.

Research hypotheses (skip new entries on a verified critical event, require more confirmation under uncertainty, cut exposure in market-wide stress) are listed and **not activated**. They do not run inside Coordinator or Risk.

The simulator remains spot-like and long-only. It is not a leveraged futures backtest. Same-bar stop-loss priority, confirmed bars, and isolated journals are unchanged.

Historical news comparison is blocked on development data because revision coverage is incomplete. The dashboard hides a valid news-versus-LLM comparison unless a saved run's own provenance status is `complete`.
