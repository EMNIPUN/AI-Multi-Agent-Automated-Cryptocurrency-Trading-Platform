# CryptoNova 76 — Architecture Audit

Phase 76 inspected the repository and left functioning components in place. The only runtime boundary added is an explicit backtest journal mode that defaults to SQLite and refuses PostgreSQL cutover.

This audit is preparation evidence. It is not development-database validation and not a production review.

## Dependency map

| Component | Entry point | Persistence | Ownership | Feature flag | Runtime state | Test coverage | Remaining gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Market Data Agent | `build_market_snapshot` in `agent/multi_agent/market_agent.py` | None. Snapshot only. | Not stored by this function. | None. | In-process. | `tests/test_phase4a_multi_agent_signals.py` | No live market dependency for the deterministic tests. |
| Trend Agent | `evaluate_trend` in `agent/multi_agent/trend_agent.py` | None. | Not stored. | None. | In-process. | Phase 4A signal tests. | Advisory news context cannot change the action. |
| Momentum Agent | `evaluate_momentum` in `agent/multi_agent/momentum_agent.py` | None. | Not stored. | None. | In-process. | Phase 4A signal tests. | RSI and volume stay inputs to the coordinator. |
| Coordinator | `coordinate` in `agent/multi_agent/coordinator.py` | Decision object only. | Not stored until the pipeline persists. | None. | In-process. `execution_allowed` is false. | Phase 4A and pipeline tests. | News flag is forced false. |
| Risk Agent | `evaluate_signal_risk` in `agent/multi_agent/risk_agent.py` | Risk state when the signal store commits. | Bound owner on the signal row. | None. | In-process veto. | Phase 4A veto, halt, and sizing tests. | Veto is not overridable by news or LLM. |
| Signal pipeline | `SignalPipeline.evaluate` in `agent/multi_agent/pipeline.py` | SQLite signal history when a store is attached. | `resolve_sot_owner_user_id`. | `SIGNAL_CLOUD_OWNER_USER_ID` for unattended persistence. | Local SQLite. Cloud sync stays gated. | `tests/test_phase4b_signal_history.py`, `tests/test_phase4c_auto_signal_engine.py`, `tests/test_phase4d_complete_local.py` | Committed development signal rows and development restart recovery were not run. |
| Signal history | `agent/multi_agent/signal_history_store.py` | SQLite file, or PostgreSQL `app.signal_history` when the source of truth is Postgres. | Owner UUID on every row. Missing owner fails closed. | `SUPABASE_SOT_ENABLED` selects the engine. Tests force it false. | Development table has zero rows. | Phase 4B–4D plus the Postgres outbox fail-closed test. | PostgreSQL outbox methods return `outbox_not_applicable_signal_history_is_authoritative`. |
| Paper broker | `PaperBroker` in `agent/paper/broker.py` | Isolated SQLite through `PaperStore`. | Resolved owner, required false for isolated stores. | `AGENT_ALLOW_LIVE=false`. Paper read API stays off. | SQLite. | `tests/test_core_paper_broker.py`, store, risk, and integration suites. | PostgreSQL paper runtime is not wired. |
| Portfolio risk | `evaluate_portfolio_entry` in `agent/paper/risk.py` | Paper SQLite risk and equity rows. | Session owner. | Portfolio mode is per backtest config. | SQLite. | `tests/test_core_paper_risk_integration.py` | Development paper sessions have no orders. |
| Historical backtest | `run_backtest` in `agent/backtest/runner.py` | Isolated `bt68a_*.sqlite3`. | Journal file, not the operator paper book. | `journal_mode` defaults to `sqlite`. | SQLite. PostgreSQL mode raises before any journal file is created. | `tests/test_core_backtest_68a.py`, `tests/test_core_76_local_migration.py` | Cutover is not enabled. |
| PostgreSQL backtest journal | `PostgresBacktestJournal` in `agent/backtest/pg_journal.py` | Schema `app` on the engine the caller supplies. | `owner_user_id` NOT NULL. | No process flag. The runner does not select it. | Code ready. Development tables absent. | `tests/test_core_75_local_journal.py`, local migration test. | Migration `20261108_0012` is not applied on development. |
| Journal export | `export_sqlite_backtest` in `agent/backtest/journal_export.py` | Reads SQLite, writes one PostgreSQL transaction. | Caller-supplied owner. | Not called by the runner. | Used only by local tests. | Parity tests. | A failed PostgreSQL write does not alter the SQLite balance. |
| Analytics | `compute_session_analytics` in `agent/paper/analytics/service.py` | Reads the paper journal. | Session scoped. | Paper read API disabled by default. | SQLite calculations. | `tests/test_core_paper_analytics.py` | Closed-trade fees exclude open-position entry fees. |
| News intelligence | `apps/api/app/news/` | Development `app.news_events` and revisions. | Existing rows only. | Collection, Telegram, and LLM flags unset. | Read path. Historical provenance is `incomplete`. | News unit tests. One Postgres integration test stays skipped. | Do not fabricate revisions. Historical backtest validity stays false. |
| LLM advisory | `agent/llm_intelligence/service.py` | `app.llm_evaluations` is empty on development. | Advisory record only. | `NEWS_LLM_ENABLED` unset. | No paid calls. | `tests/test_core_llm_69d.py` | `llm_changed_decision` stays false. |
| FastAPI | `create_app` in `apps/api/app/factory.py` | `DATABASE_URL` when the source of truth is Postgres. | JWT principal must match the bound owner. | Live trading, paper read, and news automation stay off. | API process was not required for this phase. | API foundation and route tests. | Privileged role bypasses RLS. |
| Next.js dashboard | `apps/web/src/app/*/page.tsx` | Browser calls the API. No direct database access. | Supabase browser session is a UI gate. | Public anon key only in the client. | Protected prefixes include the six review routes. | Vitest, 59 tests. | Signed-in browser session was not available. |

## Safety flags observed

A read-only development session reported:

- `AGENT_ALLOW_LIVE=false`
- `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false`
- `NEWS_LLM_ENABLED`, `NEWS_AGENT_ADVISORY_ENABLED`, `NEWS_TELEGRAM_ENABLED`, `NEWS_AUTO_COLLECTION_ENABLED`, and `NEWS_PG_INTEGRATION` unset
- `SUPABASE_SOT_ENABLED` unset in the environment file. The API default remains on for a real API process. Pytest forces it false before imports.

No flag was edited.
