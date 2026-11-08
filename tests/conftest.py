from __future__ import annotations

import os

# Offline unit tests use SQLAlchemy SQLite engines (no sqlite3 module in stores).
# Production SoT remains Supabase when SUPABASE_SOT_ENABLED=true outside pytest.
os.environ["SUPABASE_SOT_ENABLED"] = "false"

try:
    from apps.api.app.config import clear_settings_cache

    clear_settings_cache()
except Exception:  # noqa: BLE001
    pass

from agent.config import AgentSettings


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
