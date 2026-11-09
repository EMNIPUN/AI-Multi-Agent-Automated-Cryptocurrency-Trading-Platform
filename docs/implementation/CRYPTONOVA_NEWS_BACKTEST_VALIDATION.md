# CryptoNova — News Backtest Validation

**Status: BLOCKED for historical performance claims. Forward revision capture is verified.**

`app.news_event_revisions` exists and the append-only trigger is installed. A synthetic event proved:

- revision 1 recorded at classification time, not at the earlier publication time
- a duplicate material classification did not append
- a severity change appended revision 2
- an as-of time between them selected only revision 1
- UPDATE and DELETE were rejected

Those two revisions remain because they cannot be deleted. Their event id is `70b1evt26a00b9fa389`. They are test residue, not market history.

The other 10 `news_events` rows have no revisions. They were stored before `20261108_0010`. They were not backfilled and must not be treated as a complete point-in-time archive.

`GET /api/v1/backtests/shadow-status` on the restarted API returns:

- revision `20261108_0011`
- `migrations_pending=[]`
- `historical_news_backtest_valid=false`
- `provenance_status=incomplete`
- `openai_called=false`
- decisions unchanged

Shadow modes A, B, and C still annotate a finished technical backtest. They do not create a second equity curve and do not change fills. Backtest execution journals remain isolated `bt68a_*.sqlite3` files. The simulator is still long-only and spot-like.

News-aware backtesting is not historically valid for the current development news set.
