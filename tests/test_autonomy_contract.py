"""Autonomy contract projections for PAPER control plane."""

from __future__ import annotations

from agent.supervisor.autonomy_contract import (
    append_decision_queue,
    build_autonomy_snapshot,
    per_agent_runtime_status,
    protective_close_events,
    risk_feed,
)


def test_per_agent_runtime_uses_contributions_not_cloned_state() -> None:
    latest = {
        "contributions": [
            {
                "agent_id": "trend",
                "bias": "BULLISH",
                "confidence": 0.7,
                "reason_codes": ["EMA_ALIGNED"],
                "explanation": "trend up",
                "timed_out": False,
                "error": None,
            }
        ]
    }
    body = per_agent_runtime_status(
        latest_decision=latest,
        supervisor_state="RUNNING",
        paper_supervisor_enabled=True,
        heartbeat_ms=123,
    )
    trend = next(a for a in body["agents"] if a["agent_id"] == "trend")
    volume = next(a for a in body["agents"] if a["agent_id"] == "volume")
    assert trend["status"] == "ACTIVE"
    assert trend["bias"] == "BULLISH"
    assert volume["status"] == "IDLE"
    assert volume["bias"] is None
    assert body["live_orders"] is False


def test_append_decision_queue_bounded() -> None:
    data: dict = {}
    for i in range(60):
        append_decision_queue(
            data,
            {
                "decision_id": f"d{i}",
                "timestamp_ms": i,
                "action": "HOLD",
                "symbol": "BTCUSDT",
                "contributions": [],
                "decision_context": {},
            },
            limit=50,
        )
    assert len(data["decision_queue"]) == 50
    assert data["decision_queue"][0]["decision_id"] == "d10"


def test_build_autonomy_snapshot_includes_risk_and_timeline() -> None:
    status = {
        "state": "RUNNING",
        "session_id": "s1",
        "heartbeat_ms": 1,
        "latest_decision": {"action": "BUY", "decision_id": "d1", "contributions": []},
        "decision_queue": [],
        "block_new_exposure": False,
        "daily_loss_fraction": "0.01",
        "authorization": {"symbol": "HYPEUSDT"},
    }
    report = {
        "available": True,
        "equity": "100",
        "realized_pnl": "1",
        "unrealized_pnl": "0",
        "fees_paid": "0.1",
        "drawdown": "0",
        "closed_trades": 1,
        "winning_trades": 1,
        "win_rate": 1.0,
        "open_positions": 0,
        "positions": [],
        "recent_trades": [
            {
                "position_id": "p1",
                "exit_reason": "TAKE_PROFIT",
                "closed_ms": 2,
                "opened_ms": 1,
            }
        ],
        "recent_events": [],
        "pending_orders": [],
    }
    snap = build_autonomy_snapshot(
        status=status,
        report=report,
        paper_supervisor_enabled=True,
    )
    assert snap["contract_version"] == "autonomy.v1"
    assert snap["mode"] == "PAPER"
    assert snap["risk"]["halted"] is False
    assert snap["protective_events"]
    assert snap["agents"]["agent_count"] > 0


def test_risk_feed_halted() -> None:
    risk = risk_feed({"state": "HALTED", "block_new_exposure": True, "last_error": "DAILY_LOSS"}, {})
    assert risk["halted"] is True
    assert risk["live_orders"] is False


def test_protective_close_events() -> None:
    events = protective_close_events(
        {
            "recent_events": [
                {
                    "event_id": "e1",
                    "event_type": "POSITION_CLOSED",
                    "created_ms": 1,
                    "payload": {"exit_reason": "STOP_LOSS"},
                }
            ],
            "recent_trades": [],
        }
    )
    assert events[0]["protective"] is True
