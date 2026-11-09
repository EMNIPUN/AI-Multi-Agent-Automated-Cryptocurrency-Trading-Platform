"""Human-approved PAPER trade proposals for Orchestrator chat.

Stores pending proposals in memory. Approval places a paper (simulated) order only.
Never places Bybit live/testnet orders.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.backtest.execution_adapter import market_to_paper_candle
from agent.market_data import Candle
from agent.multi_agent.config import SignalPipelineConfig
from agent.multi_agent.pipeline import SignalPipeline
from agent.orchestrator.agent_registry import news_advisory_enabled_from_env, run_full_analysis
from agent.paper.auto_trade import AutomaticPaperTrader


_LOCK = threading.Lock()
_PROPOSALS: dict[str, "PaperTradeProposal"] = {}
_DEFAULT_TTL_MS = 15 * 60_000
_CHAT_JOURNAL = "data/paper_supervisor/orchestrator_chat_paper.sqlite3"


@dataclass
class PaperTradeProposal:
    proposal_id: str
    symbol: str
    category: str
    interval: str
    side: str
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    last_price: float | None
    risk_verdict: str | None
    analysis_action: str
    timing: str
    explanation: str
    created_ms: int
    expires_ms: int
    status: str = "pending"  # pending | approved | rejected | expired | failed
    paper_order_id: str | None = None
    paper_reason: str | None = None
    decision_public: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


def reset_proposals_for_tests() -> None:
    with _LOCK:
        _PROPOSALS.clear()


def _new_id() -> str:
    return f"ptp_{secrets.token_hex(6)}"


def _expire_locked(now_ms: int) -> None:
    for item in _PROPOSALS.values():
        if item.status == "pending" and now_ms >= item.expires_ms:
            item.status = "expired"


def get_proposal(proposal_id: str) -> PaperTradeProposal | None:
    with _LOCK:
        _expire_locked(int(time.time() * 1000))
        return _PROPOSALS.get(str(proposal_id or "").strip())


def latest_pending_proposal() -> PaperTradeProposal | None:
    with _LOCK:
        _expire_locked(int(time.time() * 1000))
        pending = [p for p in _PROPOSALS.values() if p.status == "pending"]
        pending.sort(key=lambda p: p.created_ms, reverse=True)
        return pending[0] if pending else None


def _format_levels(entry: Any, stop_loss: Any, take_profit: Any, side: str) -> list[str]:
    if entry is None:
        return [
            "Entry: not armed.",
            "Stop Loss (SL): not armed.",
            "Take Profit (TP): not armed.",
            f"Side: {side}.",
        ]
    return [
        f"Side: {side}.",
        f"Entry: {entry}.",
        f"Stop Loss (SL): {stop_loss}.",
        f"Take Profit (TP): {take_profit}.",
        f"Leave / exit target (TP): {take_profit}.",
    ]


def build_trade_plan_from_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Normalize analysis into a chat trade-plan payload (no order yet)."""
    action = str(analysis.get("analysis_action") or analysis.get("signal_action") or "HOLD").upper()
    entry = analysis.get("entry")
    stop_loss = analysis.get("stop_loss")
    take_profit = analysis.get("take_profit")
    levels = analysis.get("levels") if isinstance(analysis.get("levels"), dict) else {}
    if entry is None and isinstance(levels, dict):
        entry = levels.get("entry")
        stop_loss = levels.get("stop_loss")
        take_profit = levels.get("take_profit")
    last_price = analysis.get("last_price")
    if entry is None and last_price is not None and action in {"BUY", "SELL"}:
        # Fallback advisory levels if pipeline omitted them.
        price = float(last_price)
        stop_pct = 0.01
        reward_pct = 0.02
        if action == "BUY":
            entry, stop_loss, take_profit = price, price * (1 - stop_pct), price * (1 + reward_pct)
        else:
            entry, stop_loss, take_profit = price, price * (1 + stop_pct), price * (1 - reward_pct)
    risk_verdict = str(analysis.get("risk_verdict") or "").upper() or None
    timing = str(analysis.get("timing") or "")
    symbol = str(analysis.get("symbol") or "HYPEUSDT").upper()
    category = str(analysis.get("category") or "linear")
    interval = str(analysis.get("interval") or "15")
    explanation = str(analysis.get("explanation") or "")

    actionable = action in {"BUY", "SELL"} and entry is not None
    # Paper broker: BUY opens long; SELL closes long. Shorts are not opened.
    paper_placeable = actionable and action == "BUY" and risk_verdict == "APPROVED"
    advisory_only = actionable and not paper_placeable

    level_lines = _format_levels(entry, stop_loss, take_profit, action)
    return {
        "symbol": symbol,
        "category": category,
        "interval": interval,
        "side": action,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "last_price": last_price,
        "risk_verdict": risk_verdict,
        "analysis_action": action,
        "timing": timing,
        "explanation": explanation,
        "actionable": actionable,
        "paper_placeable": paper_placeable,
        "advisory_only": advisory_only,
        "awaiting_human_approval": False,
        "level_lines": level_lines,
        "decision": analysis.get("decision") if isinstance(analysis.get("decision"), dict) else {},
        "agents_ran": analysis.get("agents_ran") or [],
        "live_orders": False,
        "execution_allowed": False,
        "exchange_order_sent": False,
    }


def create_proposal_from_analysis(analysis: dict[str, Any], *, ttl_ms: int = _DEFAULT_TTL_MS) -> dict[str, Any]:
    plan = build_trade_plan_from_analysis(analysis)
    now_ms = int(time.time() * 1000)
    proposal_id = _new_id()
    proposal = PaperTradeProposal(
        proposal_id=proposal_id,
        symbol=plan["symbol"],
        category=plan["category"],
        interval=plan["interval"],
        side=plan["side"],
        entry=float(plan["entry"]) if plan["entry"] is not None else None,
        stop_loss=float(plan["stop_loss"]) if plan["stop_loss"] is not None else None,
        take_profit=float(plan["take_profit"]) if plan["take_profit"] is not None else None,
        last_price=float(plan["last_price"]) if plan["last_price"] is not None else None,
        risk_verdict=plan["risk_verdict"],
        analysis_action=plan["analysis_action"],
        timing=plan["timing"],
        explanation=plan["explanation"],
        created_ms=now_ms,
        expires_ms=now_ms + int(ttl_ms),
        status="pending" if plan["actionable"] else "failed",
        decision_public=plan.get("decision") or {},
        paper_reason=None if plan["actionable"] else "signal_not_actionable",
    )
    with _LOCK:
        _expire_locked(now_ms)
        if plan["actionable"]:
            _PROPOSALS[proposal_id] = proposal

    lines = [
        f"Trade plan for {plan['symbol']} {plan['category']} {plan['interval']}m (multi-agent).",
        plan["timing"] or f"Timing: confirm on closed {plan['interval']}m candles.",
        f"Last price: {plan['last_price']}.",
        f"Decision: {plan['analysis_action']}.",
        f"Risk verdict: {plan['risk_verdict'] or 'UNKNOWN'}.",
        *plan["level_lines"],
    ]
    if plan["explanation"]:
        lines.append(plan["explanation"])
    if plan["paper_placeable"]:
        lines.append(
            f"PAPER order ready — human approval required. Proposal id: {proposal_id}."
        )
        lines.append(
            'Reply "Approve paper trade" or "Reject paper trade" (or use the buttons).'
        )
        lines.append("This places a simulated paper order only — not Bybit live/testnet.")
        awaiting = True
    elif plan["advisory_only"] and plan["side"] == "SELL":
        lines.append(
            "Signal is SELL. Paper broker closes an existing long; it does not open shorts."
        )
        lines.append(
            f"Proposal id {proposal_id} is advisory. Approve will attempt a paper exit if a long is open."
        )
        awaiting = True
        with _LOCK:
            _PROPOSALS[proposal_id] = proposal
            proposal.status = "pending"
            proposal.paper_reason = "sell_exit_or_advisory"
    elif plan["advisory_only"]:
        lines.append(
            "Levels are advisory only — risk did not approve a paper entry. No order will be placed."
        )
        awaiting = False
    else:
        lines.append(
            "No actionable BUY/SELL levels — HOLD/BLOCKED. No paper order can be approved."
        )
        awaiting = False
    lines.append("Live Bybit orders stay locked.")

    return {
        **plan,
        **analysis,
        "proposal_id": proposal_id if awaiting or plan["actionable"] else None,
        "awaiting_human_approval": awaiting,
        "human_approval_required": awaiting,
        "entry": plan["entry"],
        "stop_loss": plan["stop_loss"],
        "take_profit": plan["take_profit"],
        "side": plan["side"],
        "paper_placeable": plan["paper_placeable"],
        "summary": "\n".join(lines),
        "live_orders": False,
        "execution_allowed": False,
        "exchange_order_sent": False,
        "execution_mode": "PAPER",
    }


def propose_paper_trade(
    *,
    symbol: str,
    category: str = "linear",
    interval: str = "15",
    candles: list[Candle],
    now_ms: int | None = None,
) -> dict[str, Any]:
    analysis = run_full_analysis(
        symbol=symbol,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=now_ms,
        data_path="orchestrator_propose_paper",
    )
    return create_proposal_from_analysis(analysis)


def reject_paper_trade(proposal_id: str) -> dict[str, Any]:
    proposal = get_proposal(proposal_id)
    if proposal is None:
        # Reject latest pending if id omitted / unknown
        with _LOCK:
            pending = [p for p in _PROPOSALS.values() if p.status == "pending"]
            pending.sort(key=lambda p: p.created_ms, reverse=True)
            proposal = pending[0] if pending else None
    if proposal is None:
        return {
            "ok": False,
            "summary": "No pending paper trade proposal to reject.",
            "live_orders": False,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    with _LOCK:
        if proposal.status != "pending":
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "status": proposal.status,
                "summary": f"Proposal {proposal.proposal_id} is already {proposal.status}.",
                "live_orders": False,
                "awaiting_human_approval": False,
            }
        proposal.status = "rejected"
    return {
        "ok": True,
        "proposal_id": proposal.proposal_id,
        "status": "rejected",
        "symbol": proposal.symbol,
        "side": proposal.side,
        "entry": proposal.entry,
        "stop_loss": proposal.stop_loss,
        "take_profit": proposal.take_profit,
        "summary": (
            f"Paper trade proposal {proposal.proposal_id} rejected.\n"
            f"Side: {proposal.side}. Entry: {proposal.entry}. SL: {proposal.stop_loss}. TP: {proposal.take_profit}.\n"
            "No paper order was sent. Live Bybit stays locked."
        ),
        "live_orders": False,
        "exchange_order_sent": False,
        "awaiting_human_approval": False,
    }


def approve_paper_trade(
    proposal_id: str | None = None,
    *,
    candles: list[Candle] | None = None,
    journal_path: str = _CHAT_JOURNAL,
) -> dict[str, Any]:
    """Place a PAPER order after human approval. Never touches Bybit private APIs."""
    proposal = get_proposal(proposal_id or "")
    if proposal is None:
        with _LOCK:
            pending = [p for p in _PROPOSALS.values() if p.status == "pending"]
            pending.sort(key=lambda p: p.created_ms, reverse=True)
            proposal = pending[0] if pending else None
    if proposal is None:
        return {
            "ok": False,
            "summary": (
                "No pending paper trade proposal.\n"
                'Ask for a trade plan first (e.g. "I want trade HYPE"), then approve.'
            ),
            "live_orders": False,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    now_ms = int(time.time() * 1000)
    if proposal.status != "pending" or now_ms >= proposal.expires_ms:
        proposal.status = "expired" if proposal.status == "pending" else proposal.status
        return {
            "ok": False,
            "proposal_id": proposal.proposal_id,
            "status": proposal.status,
            "summary": f"Proposal {proposal.proposal_id} is {proposal.status}. Run a new trade plan.",
            "live_orders": False,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    if candles is None or len(candles) < 2:
        return {
            "ok": False,
            "proposal_id": proposal.proposal_id,
            "summary": "Public candles unavailable — paper order not sent.",
            "live_orders": False,
            "exchange_order_sent": False,
            "awaiting_human_approval": True,
        }

    # Re-evaluate on fresh candles so risk cannot be bypassed by a stale proposal.
    pipe = SignalPipeline(config=SignalPipelineConfig(), persist=False)
    decision = pipe.evaluate(
        symbol=proposal.symbol,
        category=proposal.category,
        interval=proposal.interval,
        candles=candles,
        now_ms=now_ms,
        data_path="orchestrator_approve_paper",
        news_advisory_enabled=news_advisory_enabled_from_env(),
    )
    action = decision.action.value if hasattr(decision.action, "value") else str(decision.action)
    verdict = decision.risk.verdict.value if hasattr(decision.risk.verdict, "value") else str(decision.risk.verdict)

    trader = AutomaticPaperTrader(journal_path, now_ms=now_ms)
    candle = market_to_paper_candle(candles[-1], symbol=proposal.symbol, interval=proposal.interval)
    result = trader.apply_decision(decision, candle)

    order_id = result.get("order_id")
    reason = str(result.get("reason") or "")
    reason_u = reason.upper()
    # NO_OPEN_LONG / NOT_ACTIONABLE are not successful entries.
    fail_reasons = {
        "NO_OPEN_LONG",
        "NOT_ACTIONABLE",
        "MISSING_DECISION",
        "NO_CANDLES",
        "HOLD_IGNORED",
        "BLOCKED_IGNORED",
        "RISK_VETO_IGNORED",
        "RISK_NOT_APPROVED",
        "INSUFFICIENT_FUNDS",
        "SESSION_INACTIVE",
    }
    submit_ok = bool(order_id) and reason_u not in fail_reasons
    if reason_u in {"DUPLICATE_SIGNAL", "ORDER_ACCEPTED", "ACCEPTED", "SUBMITTED", "PENDING_NEW"}:
        submit_ok = True

    with _LOCK:
        if submit_ok:
            proposal.status = "approved"
            proposal.paper_order_id = order_id
            proposal.paper_reason = reason
        else:
            proposal.status = "failed" if reason_u in fail_reasons else "approved"
            proposal.paper_order_id = order_id
            proposal.paper_reason = reason or "NOT_ACTIONABLE"
            if proposal.status == "approved" and order_id:
                submit_ok = True

    lines = [
        f"Human-approved PAPER execution for proposal {proposal.proposal_id}.",
        f"Symbol: {proposal.symbol}.",
        f"Proposed side: {proposal.side}. Re-check action: {action}. Risk: {verdict}.",
        f"Entry: {proposal.entry}. Stop Loss (SL): {proposal.stop_loss}. Take Profit (TP): {proposal.take_profit}.",
        f"Paper result: {reason}. Order id: {result.get('order_id') or 'none'}.",
        f"Open positions: {result.get('open_positions')}. Available: {result.get('available_balance')}.",
    ]
    if action == "SELL" and not result.get("order_id"):
        lines.append(
            "SELL with no open long does not open a short in paper mode."
        )
    if action == "BUY" and not result.get("order_id"):
        lines.append(
            "BUY was not accepted by the paper broker (see reason). Levels remain advisory."
        )
    lines.append("Bybit live/testnet order was NOT sent.")

    return {
        "ok": bool(submit_ok),
        "proposal_id": proposal.proposal_id,
        "status": proposal.status,
        "symbol": proposal.symbol,
        "side": action,
        "entry": proposal.entry,
        "stop_loss": proposal.stop_loss,
        "take_profit": proposal.take_profit,
        "risk_verdict": verdict,
        "analysis_action": action,
        "paper": result,
        "order_id": result.get("order_id"),
        "awaiting_human_approval": False,
        "execution_mode": "PAPER",
        "live_orders": False,
        "execution_allowed": False,
        "exchange_order_sent": False,
        "summary": "\n".join(lines),
    }
