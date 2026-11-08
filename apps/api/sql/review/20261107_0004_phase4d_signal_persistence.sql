-- PROPOSED Phase 4D DDL — DO NOT APPLY without operator approval.
-- Source of truth for review: alembic/versions_proposed/20261107_0004_phase4d_signal_persistence.py
-- Current Alembic HEAD remains: 20261105_0003
--
-- Future-only (NOT in this migration): historical_candle_*, backtest_*, paper_*, trading_journal_*
-- Local-only (NOT moved to Postgres): scheduler_lock, paper_risk_state singleton (authoritative local)

-- See PHASE_4D_DATABASE_SCHEMA.md for full column rationale.
;