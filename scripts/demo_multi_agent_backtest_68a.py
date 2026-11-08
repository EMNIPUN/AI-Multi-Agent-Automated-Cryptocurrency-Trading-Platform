#!/usr/bin/env python3
"""
Prompt 68A — Deterministic multi-agent historical backtest demo.

Uses an offline synthetic OHLCV fixture, the real SignalPipeline, and an
isolated paper journal. No live orders, private Bybit calls, OpenAI, or
remote SoT writes.

HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Offline isolation before any store imports resolve settings.
os.environ["SUPABASE_SOT_ENABLED"] = "false"
os.environ.setdefault("AGENT_ALLOW_LIVE", "false")

from agent.backtest.artifacts import persist_run_artifact
from agent.backtest.config import BacktestConfig, DataSourceKind, RiskMode
from agent.backtest.data import save_fixture_file, synthetic_trend_candles
from agent.backtest.report import print_summary
from agent.backtest.runner import run_backtest
from agent.paper.integration import PAPER_BROKER_AUTO_ATTACH, PAPER_PORTFOLIO_RISK_ENABLED


def main() -> int:
    assert PAPER_BROKER_AUTO_ATTACH is False
    assert PAPER_PORTFOLIO_RISK_ENABLED is False

    out_dir = ROOT / "data" / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = out_dir / "demo_btc_15m_68a_fixture.json"
    candles = synthetic_trend_candles(n=240, start_price=40_000.0)
    save_fixture_file(
        fixture,
        candles,
        meta={
            "symbol": "BTCUSDT",
            "interval": "15",
            "market_type": "spot",
            "provenance": "synthetic_offline_demo_68a",
            "label": "SYNTHETIC HISTORICAL FIXTURE — NOT LIVE STREAM",
        },
    )

    cfg = BacktestConfig(
        symbol="BTCUSDT",
        market_type="spot",
        interval="15",
        initial_capital=Decimal("10000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        risk_mode=RiskMode.SIGNAL_ONLY,
        data_source=DataSourceKind.FIXTURE_FILE,
        dataset_path=str(fixture),
        grace_ms=2_000,
    )
    result = run_backtest(cfg, journal_dir=out_dir)
    report_path = persist_run_artifact(result, results_dir=out_dir)
    print_summary(result)
    print(f"fixture={fixture}")
    print(f"report={report_path}")
    print(f"journal={result.journal_path}")
    print("PAPER_BROKER_AUTO_ATTACH remains False. No exchange/cloud writes.")
    # Compact machine-readable status line for CI/scripts.
    print(
        json.dumps(
            {
                "status": result.status.value,
                "result_hash": result.result_hash,
                "evaluations": result.counters.get("total_agent_evaluations"),
                "closed_trades": (result.analytics or {}).get("closed_trades"),
            },
            separators=(",", ":"),
        )
    )
    return 0 if result.status.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
