"""Human-approved paper trade proposals — no live Bybit orders."""

from __future__ import annotations

from pathlib import Path

from agent.market_data import Candle
from agent.orchestrator.guard import ALLOWED_TOOLS, validate_tool_call
from agent.orchestrator.trade_proposals import (
    approve_paper_trade,
    create_proposal_from_analysis,
    reject_paper_trade,
    reset_proposals_for_tests,
)


def _candles(n: int = 220, start_price: float = 70.0) -> list[Candle]:
    interval_ms = 15 * 60_000
    base = 1_700_000_000_000
    rows: list[Candle] = []
    for i in range(n):
        px = start_price + i * 0.05
        start = base + i * interval_ms
        rows.append(
            Candle(
                start=start,
                open=px,
                high=px + 0.2,
                low=px - 0.1,
                close=px + 0.02,
                volume=1000.0,
            )
        )
    return rows


def test_propose_tools_are_allowlisted() -> None:
    assert "propose_paper_trade" in ALLOWED_TOOLS
    assert "approve_paper_trade" in ALLOWED_TOOLS
    assert "reject_paper_trade" in ALLOWED_TOOLS
    assert validate_tool_call(
        "propose_paper_trade",
        {"symbol": "HYPEUSDT", "category": "linear", "interval": "15"},
    ) is None
    assert validate_tool_call("approve_paper_trade", {"proposal_id": ""}) is None
    assert validate_tool_call("approve_paper_trade", {"proposal_id": "ptp_abcd1234ef"}) is None
    assert validate_tool_call("approve_paper_trade", {"proposal_id": "bad"}) == "tool_arguments_invalid"


def test_create_proposal_surfaces_entry_sl_tp_and_stays_paper() -> None:
    reset_proposals_for_tests()
    analysis = {
        "symbol": "HYPEUSDT",
        "category": "linear",
        "interval": "15",
        "analysis_action": "BUY",
        "signal_action": "BUY",
        "last_price": 75.0,
        "entry": 75.0,
        "stop_loss": 74.0,
        "take_profit": 77.0,
        "risk_verdict": "APPROVED",
        "timing": "Timing: use confirmed 15m candle closes.",
        "explanation": "Directional conviction high",
        "agents_ran": ["market", "trend", "momentum", "strategy", "risk"],
        "decision": {},
        "live_orders": False,
    }
    body = create_proposal_from_analysis(analysis)
    assert body["awaiting_human_approval"] is True
    assert body["entry"] == 75.0
    assert body["stop_loss"] == 74.0
    assert body["take_profit"] == 77.0
    assert "Entry: 75.0" in body["summary"]
    assert "Stop Loss (SL): 74.0" in body["summary"]
    assert "Take Profit (TP): 77.0" in body["summary"]
    assert body["live_orders"] is False
    assert body["exchange_order_sent"] is False
    assert str(body["proposal_id"]).startswith("ptp_")


def test_reject_and_approve_without_live(tmp_path: Path) -> None:
    reset_proposals_for_tests()
    analysis = {
        "symbol": "HYPEUSDT",
        "category": "linear",
        "interval": "15",
        "analysis_action": "BUY",
        "last_price": 75.0,
        "entry": 75.0,
        "stop_loss": 74.0,
        "take_profit": 77.0,
        "risk_verdict": "APPROVED",
        "timing": "Timing: confirmed 15m.",
        "explanation": "ok",
        "decision": {},
    }
    proposed = create_proposal_from_analysis(analysis)
    pid = proposed["proposal_id"]
    rejected = reject_paper_trade(pid)
    assert rejected["ok"] is True
    assert rejected["status"] == "rejected"
    assert rejected["exchange_order_sent"] is False

    proposed2 = create_proposal_from_analysis(analysis)
    pid2 = proposed2["proposal_id"]
    journal = tmp_path / "chat_paper.sqlite3"
    approved = approve_paper_trade(pid2, candles=_candles(), journal_path=str(journal))
    assert approved["live_orders"] is False
    assert approved["exchange_order_sent"] is False
    assert approved["awaiting_human_approval"] is False
    assert "Bybit live" in approved["summary"] or "NOT sent" in approved["summary"]
