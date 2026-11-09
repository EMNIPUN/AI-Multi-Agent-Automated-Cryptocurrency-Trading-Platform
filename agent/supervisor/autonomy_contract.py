"""Stable Autonomy contract projections for PAPER control plane APIs/UI."""

from __future__ import annotations

from typing import Any

from agent.multi_agent.config import STRATEGY_VERSION
from agent.orchestrator.agent_registry import REGISTRY, list_agents


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def append_decision_queue(
    data: dict[str, Any],
    decision_public: dict[str, Any] | None,
    *,
    limit: int = 50,
) -> None:
    """Persist a bounded recent-decision ring on supervisor state."""
    if not isinstance(decision_public, dict):
        return
    queue = _as_list(data.get("decision_queue"))
    entry = {
        "decision_id": decision_public.get("decision_id"),
        "timestamp_ms": decision_public.get("timestamp_ms"),
        "action": decision_public.get("action"),
        "symbol": decision_public.get("symbol"),
        "category": decision_public.get("category"),
        "interval": decision_public.get("interval"),
        "signal_strength": decision_public.get("signal_strength"),
        "directional_conviction": decision_public.get("directional_conviction"),
        "explanation": decision_public.get("explanation"),
        "reason_codes": decision_public.get("reason_codes") or [],
        "risk_verdict": (_as_dict(decision_public.get("risk")).get("verdict")),
        "levels": decision_public.get("levels"),
        "contributions": decision_public.get("contributions") or [],
        "strategy_version": decision_public.get("strategy_version"),
        "calibration_profile_id": _as_dict(decision_public.get("decision_context")).get(
            "calibration_profile_id"
        ),
        "score_kind": _as_dict(_as_dict(decision_public.get("decision_context")).get("consensus")).get(
            "score_kind"
        ),
    }
    queue.append(entry)
    data["decision_queue"] = queue[-limit:]


def protective_close_events(report: dict[str, Any]) -> list[dict[str, Any]]:
    """First-class SL/TP and signal-close events from journal report."""
    events = []
    for event in _as_list(report.get("recent_events")):
        if not isinstance(event, dict):
            continue
        et = str(event.get("event_type") or "")
        payload = _as_dict(event.get("payload"))
        reason = str(payload.get("exit_reason") or payload.get("reason") or "")
        if et == "POSITION_CLOSED" or reason.upper() in {
            "STOP_LOSS",
            "TAKE_PROFIT",
            "SIGNAL_SELL",
            "SELL",
            "SL",
            "TP",
        }:
            events.append(
                {
                    "event_id": event.get("event_id"),
                    "event_type": et,
                    "created_ms": event.get("created_ms"),
                    "exit_reason": reason or None,
                    "payload": payload,
                    "protective": reason.upper() in {"STOP_LOSS", "TAKE_PROFIT", "SL", "TP"},
                }
            )
    for trade in _as_list(report.get("recent_trades")):
        if not isinstance(trade, dict):
            continue
        reason = str(trade.get("exit_reason") or "")
        if not reason:
            continue
        events.append(
            {
                "event_id": f"trade_{trade.get('position_id')}",
                "event_type": "POSITION_CLOSED",
                "created_ms": trade.get("closed_ms"),
                "exit_reason": reason,
                "payload": trade,
                "protective": reason.upper() in {"STOP_LOSS", "TAKE_PROFIT", "SL", "TP"},
            }
        )
    # Dedupe by event_id preserving order.
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in events:
        key = str(item.get("event_id") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out[-40:]


def position_timeline(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered open + recently closed positions for progress tracking."""
    rows: list[dict[str, Any]] = []
    for pos in _as_list(report.get("positions")):
        if isinstance(pos, dict):
            rows.append({**pos, "timeline_kind": "open"})
    for trade in _as_list(report.get("recent_trades")):
        if isinstance(trade, dict):
            rows.append({**trade, "timeline_kind": "closed"})
    rows.sort(key=lambda row: int(row.get("opened_ms") or row.get("closed_ms") or 0), reverse=True)
    return rows[:40]


def per_agent_runtime_status(
    *,
    latest_decision: dict[str, Any] | None,
    supervisor_state: str,
    paper_supervisor_enabled: bool,
    heartbeat_ms: int = 0,
) -> dict[str, Any]:
    """Honest per-agent projection from latest contributions (no cloned heartbeats)."""
    contrib_by_id: dict[str, dict[str, Any]] = {}
    for item in _as_list(_as_dict(latest_decision).get("contributions")):
        if isinstance(item, dict) and item.get("agent_id"):
            contrib_by_id[str(item["agent_id"])] = item

    agents: list[dict[str, Any]] = []
    for desc in REGISTRY:
        contrib = contrib_by_id.get(desc.agent_id)
        if contrib is not None:
            status = "ERROR" if contrib.get("error") or contrib.get("timed_out") else "ACTIVE"
            agents.append(
                {
                    "agent_id": desc.agent_id,
                    "label": desc.label,
                    "role": desc.role,
                    "places_orders": desc.places_orders,
                    "status": status,
                    "bias": contrib.get("bias"),
                    "confidence": contrib.get("confidence"),
                    "reason_codes": contrib.get("reason_codes") or [],
                    "explanation": contrib.get("explanation"),
                    "timed_out": bool(contrib.get("timed_out")),
                    "error": contrib.get("error"),
                    "source": "latest_decision_contribution",
                }
            )
        else:
            # Registered but no contribution in last cycle — do not invent RUNNING.
            mapped = {
                "strategy": "coordinator",
                "execution": "gateway",
                "performance": "journal",
                "reliability": "supervisor",
                "portfolio": "journal",
                "news": "advisory",
            }.get(desc.agent_id)
            agents.append(
                {
                    "agent_id": desc.agent_id,
                    "label": desc.label,
                    "role": desc.role,
                    "places_orders": desc.places_orders,
                    "status": "IDLE" if paper_supervisor_enabled else "DISABLED",
                    "bias": None,
                    "confidence": None,
                    "reason_codes": [],
                    "explanation": (
                        f"No contribution in latest decision"
                        f"{f' ({mapped})' if mapped else ''}."
                    ),
                    "timed_out": False,
                    "error": None,
                    "source": "registry_only",
                }
            )

    return {
        "agents": agents,
        "agent_count": len(agents),
        "supervisor_state": supervisor_state,
        "paper_supervisor_enabled": paper_supervisor_enabled,
        "heartbeat_ms": heartbeat_ms,
        "strategy_version": STRATEGY_VERSION,
        "execution_mode": "PAPER",
        "live_orders": False,
        "execution_allowed": False,
        "exchange_order_sent": False,
        "shared_spine": "SignalPipeline",
        "llm_changed_decision": False,
        "news_changed_decision": False,
        "honesty_note": (
            "Per-agent bias/confidence come from the latest pipeline contributions only. "
            "Agents without a contribution are IDLE/DISABLED — not mirrored as RUNNING."
        ),
    }


def risk_feed(status: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    """PAPER-only risk facts for Risk Center and GlobalStatusBar."""
    report = report or {}
    halted = str(status.get("state") or "") == "HALTED" or bool(status.get("block_new_exposure"))
    open_positions = int(report.get("open_positions") or 0)
    return {
        "mode": "PAPER",
        "live_orders": False,
        "execution_allowed": False,
        "supervisor_state": status.get("state"),
        "halted": halted,
        "block_new_exposure": bool(status.get("block_new_exposure")),
        "halt_reason": status.get("last_error") or status.get("last_reason"),
        "daily_loss_fraction": status.get("daily_loss_fraction"),
        "drawdown_fraction": status.get("drawdown_fraction"),
        "daily_loss_limit_fraction": status.get("daily_loss_limit_fraction") or "0.03",
        "drawdown_limit_fraction": status.get("drawdown_limit_fraction") or "0.10",
        "open_exposure_positions": open_positions,
        "equity": report.get("equity"),
        "drawdown": report.get("drawdown"),
        "peak_equity": report.get("peak_equity"),
        "cooldown_note": "Paper risk cooldown is enforced inside SignalRiskState / broker.",
        "source": "paper_supervisor",
        "label": "PAPER risk facts only — not exchange margin",
    }


def build_autonomy_snapshot(
    *,
    status: dict[str, Any],
    report: dict[str, Any],
    paper_supervisor_enabled: bool,
    decision_queue: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Single Autonomy contract payload for /autonomy ops desk."""
    latest = _as_dict(status.get("latest_decision"))
    queue = decision_queue if decision_queue is not None else _as_list(status.get("decision_queue"))
    if not queue and latest:
        queue = [latest]
    agents = per_agent_runtime_status(
        latest_decision=latest or None,
        supervisor_state=str(status.get("state") or "STOPPED"),
        paper_supervisor_enabled=paper_supervisor_enabled,
        heartbeat_ms=int(status.get("heartbeat_ms") or 0),
    )
    risk = risk_feed(status, report)
    auth = _as_dict(status.get("authorization"))
    return {
        "contract_version": "autonomy.v1",
        "enabled": paper_supervisor_enabled,
        "mode": "PAPER",
        "live_orders": False,
        "testnet_orders": False,
        "execution_allowed": False,
        "exchange_order_sent": False,
        "mainnet_locked": True,
        "strategy_version": STRATEGY_VERSION,
        "session": {
            "state": status.get("state"),
            "session_id": status.get("session_id") or report.get("session_id"),
            "authorization": auth,
            "heartbeat_ms": status.get("heartbeat_ms"),
            "worker_running": bool(status.get("worker_running")),
            "last_action": status.get("last_action"),
            "last_reason": status.get("last_reason"),
            "last_error": status.get("last_error"),
            "worker_health": (
                "ok"
                if paper_supervisor_enabled and bool(status.get("worker_running"))
                else ("disabled" if not paper_supervisor_enabled else "offline")
            ),
        },
        "worker_running": bool(status.get("worker_running")),
        "latest_decision": latest or None,
        "decision_queue": queue[-50:],
        "open_position": (_as_list(report.get("positions")) or [None])[0],
        "position_timeline": position_timeline(report),
        "protective_events": protective_close_events(report),
        "fills_blotter": _as_list(report.get("recent_trades"))[:25],
        "pending_orders": _as_list(report.get("pending_orders")),
        "journal": {
            "available": bool(report.get("available")),
            "equity_source": report.get("equity_source") or "paper_journal",
            "exchange_equity_included": False,
            "equity": report.get("equity"),
            "realized_pnl": report.get("realized_pnl"),
            "unrealized_pnl": report.get("unrealized_pnl"),
            "fees_paid": report.get("fees_paid"),
            "drawdown": report.get("drawdown"),
            "closed_trades": report.get("closed_trades"),
            "winning_trades": report.get("winning_trades"),
            "win_rate": report.get("win_rate"),
        },
        "agents": agents,
        "risk": risk,
        "agent_registry": list_agents(),
        "honesty_note": (
            "Calibrated scores are historical agreement only — not guaranteed win probability. "
            "LLM/news remain advisory and cannot change BUY/SELL."
        ),
    }
