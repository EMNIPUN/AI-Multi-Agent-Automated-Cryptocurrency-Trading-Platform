# CryptoNova 77–84 — Status

Phase 77 applied the prepared development migration and proved one journal write. Phases 78–84 were advanced only where that could be done without live orders, credential changes, paid model calls, or a production deployment.

## 77 — Development Supabase migration and integration

**Applied on development.**

- Project checked by the existing Alembic guard: `wmirifmgaftassgrfbyl`, session pooler.
- Migration file checksum unchanged: `79d1197e675da8dd8dc057670af762a23e385ddcb1bcaf26db6b66c0a4cb11d5`.
- Fresh logical backup of the 44 `app` tables, taken while revision was still `20261108_0011`, is in gitignored `data/backups/77_pre_0012_20261108T190406Z`.
- Alembic upgraded `20261108_0011` → `20261108_0012`. The approval flag was set only for that process. `.env` was not changed.
- After the upgrade, all six `backtest_exec_*` tables have row security enabled and forced.
- One isolated BTCUSDT 15-minute SQLite backtest was exported into the new journal and replayed. Fill count and fill fees matched. Paper sessions stayed 3. Paper orders, paper fills, and signal history stayed 0. News stayed 10 events and 2 revisions.

Development parity run, synthetic fixture only:

| Field | Value |
| --- | --- |
| Run id | `bt_36003df7f5b04105` |
| Fills | 5 |
| Fill fees | `50.340052130000` |
| Closed-trade fees | `40.22621097` |
| Closed trades | 2 |
| Open positions | 1 |
| Net realized PnL | `134.08917620` |
| Result hash | `b39a82397608f1c496afd68fc882c971cc048fa0aa7be30d9f33cca3b2b0f64b` |

The closed-trade fee gap is the same expected difference as Phase 76: open-position entry fees are not closed-trade performance.

The runner default remains SQLite. API jobs export to PostgreSQL only when `CRYPTONOVA_BACKTEST_JOURNAL=postgres`. That flag is not set. A PostgreSQL request without a journal still fails before creating a file. An export failure is a failed run, and database URLs are not copied into the error.

Signed-in dashboards and development signal restart were not run.

The shadow-status check now treats revision `20261108_0012` as a successful read-only probe. `historical_news_backtest_valid` stays false and no model is called.

Backend acceptance after that assertion update: 697 passed, 0 failed, 1 skipped. The skip remains the development news integration test, which would write fixture rows.

## 78 — Multi-agent and news/AI runtime

**Local behavior remains verified. Paid runtime was not started.**

The market → trend → momentum → coordinator → risk path is unchanged. `execution_allowed`, `news_changed_decision`, and `llm_changed_decision` stay false. News collection, Telegram, and LLM calls stay off. Historical news provenance is still incomplete, so a news-aware backtest is still not valid.

## 79 — Strategy research

**Recorded. Not optimized. Not a profitability result.**

No strategy rule was changed. The numbers above come from `synthetic_trend_candles`, which is a rising fixture. A positive realized PnL on that fixture does not say anything about live markets.

## 80 — Risk and security acceptance

**Still deferred for credential and grant work. Not accepted for production or live trading.**

Password rotation, role creation, and GRANT/REVOKE were not performed. The new journal tables force RLS, and the privileged development role still bypasses RLS. That remains a blocker.

`AGENT_ALLOW_LIVE` stays false.

## 81 — Extended paper trading

**One simulated journal was stored. The development paper book was not extended.**

The parity run is a 230-candle simulated session in the new backtest journal. The three existing paper sessions were not given orders or fills. Local SQLite paper tests remain the accounting suite.

## 82 — Bybit testnet validation

**Public connectivity only. No orders.**

`https://api.bybit.com/v5/market/time` and `https://api-testnet.bybit.com/v5/market/time` both returned HTTP 200. No private API key was used. No testnet or mainnet order was submitted.

## 83 — Deployment and monitoring

**Not deployed.**

Production deployment was not performed. Existing API health and backtest job status remain the monitoring surface. Security remediation is still required before a deployment claim.

## 84 — Controlled live pilot

**Not started.**

Live orders stay disabled. A live pilot needs the deferred security work, a separate explicit order approval, and `AGENT_ALLOW_LIVE` left false until that approval exists.
