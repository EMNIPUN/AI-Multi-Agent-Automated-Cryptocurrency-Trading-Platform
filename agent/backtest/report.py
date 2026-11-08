"""Reproducible backtest report serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent.backtest.models import BacktestResult


def deterministic_result_payload(result: BacktestResult) -> dict[str, Any]:
    """
    Payload used for result_hash — excludes wall-clock and ephemeral UUIDs.

    Paper store position/order IDs are random; strip them so identical sims match.
    """
    public = result.to_public_dict()
    for key in ("created_ms", "result_hash", "run_id", "journal_path", "session_id"):
        public.pop(key, None)

    analytics = public.get("analytics")
    if isinstance(analytics, dict):
        analytics = dict(analytics)
        analytics.pop("session_id", None)
        trades = analytics.get("trades")
        if isinstance(trades, list):
            cleaned_trades = []
            for t in trades:
                if not isinstance(t, dict):
                    continue
                row = dict(t)
                row.pop("position_id", None)
                cleaned_trades.append(row)
            analytics["trades"] = cleaned_trades
        opens = analytics.get("open_position_summaries")
        if isinstance(opens, list):
            cleaned_opens = []
            for p in opens:
                if not isinstance(p, dict):
                    continue
                row = dict(p)
                row.pop("position_id", None)
                cleaned_opens.append(row)
            analytics["open_position_summaries"] = cleaned_opens
        public["analytics"] = analytics

    executions = public.get("executions")
    if isinstance(executions, list):
        public["executions"] = [
            {k: v for k, v in e.items() if k != "order_id"}
            if isinstance(e, dict)
            else e
            for e in executions
        ]
    return public


def compute_result_hash(result: BacktestResult) -> str:
    payload = deterministic_result_payload(result)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_json_report(result: BacktestResult, path: str | Path) -> Path:
    """Write report JSON atomically (tmp + replace). Does not alter result_hash."""
    from agent.backtest.artifacts import atomic_write_text

    out = Path(path)
    payload = json.dumps(result.to_public_dict(), indent=2, sort_keys=True)
    atomic_write_text(out, payload)
    return out


def print_summary(result: BacktestResult) -> None:
    c = result.counters
    a = result.analytics or {}
    print("=" * 72)
    print(result.performance_label)
    print("=" * 72)
    print(f"status={result.status.value}  run_id={result.run_id}")
    print(
        f"dataset={result.dataset.symbol} {result.dataset.interval}m "
        f"candles={result.dataset.candle_count} hash={result.dataset.content_hash[:16]}…"
    )
    print(
        f"evaluations={c.get('total_agent_evaluations')} "
        f"BUY={c.get('buy_signals')} SELL={c.get('sell_signals')} "
        f"HOLD={c.get('hold_signals')} BLOCKED={c.get('blocked_signals')}"
    )
    print(
        f"orders submitted={c.get('submitted_simulated_orders')} "
        f"filled={c.get('filled_orders')} rejected={c.get('rejected_orders')}"
    )
    if a and "error" not in a:
        print(
            f"closed_trades={a.get('closed_trades')} open={a.get('open_positions')} "
            f"net_realized_pnl={a.get('net_realized_pnl')} {a.get('currency', 'USDT')}"
        )
        wr = a.get("win_rate_pct") or {}
        pf = a.get("profit_factor") or {}
        print(
            f"win_rate={wr.get('status')}:{wr.get('value')} "
            f"profit_factor={pf.get('status')}:{pf.get('value')} "
            f"fees={a.get('total_fees')}"
        )
    print(
        f"final available={result.final_available_balance} "
        f"reserved={result.final_reserved_capital} "
        f"marked_equity={result.final_marked_equity}"
    )
    print(f"result_hash={result.result_hash}")
    if result.data_quality_warnings:
        print("warnings:")
        for w in result.data_quality_warnings[:12]:
            print(f"  - {w}")
    print("=" * 72)
