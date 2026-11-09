# CryptoNova 72 — Historical News Validation

Live `GET /api/v1/news/status` returned `historical_provenance=incomplete` and `enabled=false`.

Live `GET /api/v1/backtests/shadow-status` returned:

- `last_verified_development_revision=20261108_0011`
- `revision_probe=ok`
- `historical_news_backtest_valid=false`
- `openai_called=false`
- `decisions_unchanged=true`

Catalog: `news_events=10`, `news_event_revisions=2`. The two revisions are the append-only residue from the earlier integration check. They were not deleted. The 10 events stored before revision archiving have no reconstructed history. No timestamps or classifications were fabricated.

New classifications go through `append_event_revision` inside the article transaction. A duplicate content hash is not inserted again. A missing revision table rolls back only the savepoint.

Point-in-time selection in `build_historical_news_context` includes a revision only when its availability timestamps are at or before the decision time. `refuse_latest_row_as_history` does not treat the current row as the past. `historical_news_backtest_valid` stays false while provenance is incomplete.

Valid archive behavior applies only to events written after `20261108_0010` with complete availability timestamps. The older 10 events are an incomplete period. News-performance claims for that period are not valid.
