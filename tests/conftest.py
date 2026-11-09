from __future__ import annotations

import os

import pytest

# Offline unit tests use SQLAlchemy SQLite engines (no sqlite3 module in stores).
# Production SoT remains Supabase when SUPABASE_SOT_ENABLED=true outside pytest.
os.environ["SUPABASE_SOT_ENABLED"] = "false"


@pytest.fixture(autouse=True)
def _reset_orchestrator_chat_state() -> None:
    """Futures intake / live proposals are process-global — clear between tests."""
    try:
        from agent.orchestrator.analysis_memory import reset_analysis_memory_for_tests
        from agent.orchestrator.futures_intake import reset_futures_intake_for_tests
        from agent.orchestrator.live_trade_proposals import reset_live_proposals_for_tests

        reset_futures_intake_for_tests()
        reset_live_proposals_for_tests()
        reset_analysis_memory_for_tests()
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        from agent.orchestrator.analysis_memory import reset_analysis_memory_for_tests
        from agent.orchestrator.futures_intake import reset_futures_intake_for_tests
        from agent.orchestrator.live_trade_proposals import reset_live_proposals_for_tests

        reset_futures_intake_for_tests()
        reset_live_proposals_for_tests()
        reset_analysis_memory_for_tests()
    except Exception:  # noqa: BLE001
        pass

try:
    from apps.api.app.config import clear_settings_cache

    clear_settings_cache()
except Exception:  # noqa: BLE001
    pass

from agent.config import AgentSettings

# Developer .env may enable news feeds and the paper supervisor. Unit tests
# expect those gates to stay at their code defaults unless a test sets them.
for _leaked in (
    "NEWS_RSS_FEED_URLS",
    "NEWS_COLLECTION_ENABLED",
    "NEWS_READ_API_ENABLED",
    "NEWS_AGENT_ADVISORY_ENABLED",
    "NEWS_ALERTS_ENABLED",
    "NEWS_LLM_ENABLED",
    "NEWS_AUTO_COLLECTION_ENABLED",
    "NEWS_TELEGRAM_ENABLED",
    "CRYPTONOVA_PAPER_SUPERVISOR",
):
    os.environ.pop(_leaked, None)
clear_settings_cache()


def make_settings(**overrides) -> AgentSettings:
    base = dict(
        enabled=True,
        dry_run=True,
        allow_live=False,
        category="linear",
        symbols=("HYPEUSDT",),
        interval="15",
        poll_seconds=60,
        risk_pct_equity=1.0,
        max_open_positions=1,
        daily_loss_pct=3.0,
        leverage=3,
        ema_fast=9,
        ema_slow=21,
        rsi_period=14,
        rsi_overbought=70.0,
        rsi_oversold=30.0,
        take_profit_pct=1.5,
        stop_loss_pct=1.0,
        candle_limit=120,
        candle_finalize_grace_ms=2_000,
        max_clock_skew_ms=5_000,
        max_candle_staleness_ms=0,
    )
    base.update(overrides)
    return AgentSettings(**base)
