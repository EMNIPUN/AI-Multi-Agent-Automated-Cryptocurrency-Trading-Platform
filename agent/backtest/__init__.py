"""
Deterministic multi-agent historical backtesting (Prompt 68A).

HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE.
Isolated local journal only; never auto-attaches to live paper/cloud SoT.
"""

from __future__ import annotations

from agent.backtest.config import BacktestConfig, BACKTEST_ENGINE_VERSION
from agent.backtest.models import BacktestResult, DatasetIdentity
from agent.backtest.runner import run_backtest

__all__ = [
    "BACKTEST_ENGINE_VERSION",
    "BacktestConfig",
    "BacktestResult",
    "DatasetIdentity",
    "run_backtest",
]
