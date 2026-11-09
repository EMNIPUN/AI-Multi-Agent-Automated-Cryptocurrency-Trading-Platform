"""Human-approved MAINNET live trade proposals for Orchestrator chat.

Every live order requires an explicit Approve in chat. Proposals expire.
Uses LiveBybitExecutionAdapter only when live_mutate_allowed().
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.market_data import Candle
from agent.multi_agent.config import SignalPipelineConfig
from agent.multi_agent.pipeline import SignalPipeline
from agent.orchestrator.agent_registry import news_advisory_enabled_from_env, run_full_analysis
from agent.orchestrator.trade_proposals import build_trade_plan_from_analysis


_LOCK = threading.Lock()
_PROPOSALS: dict[str, "LiveTradeProposal"] = {}
_DEFAULT_TTL_MS = 10 * 60_000


@dataclass
class LiveTradeProposal:
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
    qty: str
    created_ms: int
    expires_ms: int
    status: str = "pending"  # pending | approved | rejected | expired | failed
    intent: str = "open"  # open | close | cancel_orders
    reduce_only: bool = False
    position_side: str | None = None
    order_type: str = "Market"  # Market | Limit
    leverage: int | None = None
    limit_price: float | None = None
    exchange_order_id: str | None = None
    client_order_id: str | None = None
    fail_reason: str | None = None
    decision_public: dict[str, Any] = field(default_factory=dict)
    open_order_ids: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


def reset_live_proposals_for_tests() -> None:
    with _LOCK:
        _PROPOSALS.clear()


def _new_id() -> str:
    return f"ltp_{secrets.token_hex(6)}"


def _expire_locked(now_ms: int) -> None:
    for item in _PROPOSALS.values():
        if item.status == "pending" and now_ms >= item.expires_ms:
            item.status = "expired"


def get_live_proposal(proposal_id: str) -> LiveTradeProposal | None:
    with _LOCK:
        _expire_locked(int(time.time() * 1000))
        return _PROPOSALS.get(str(proposal_id or "").strip())


def latest_pending_live_proposal() -> LiveTradeProposal | None:
    with _LOCK:
        _expire_locked(int(time.time() * 1000))
        pending = [p for p in _PROPOSALS.values() if p.status == "pending"]
        pending.sort(key=lambda p: p.created_ms, reverse=True)
        return pending[0] if pending else None


def _default_qty(symbol: str, entry: float | None) -> str:
    """Conservative notional sizing for linear USDT perps (~25 USDT)."""
    price = float(entry or 0) or 1.0
    notional = 25.0
    qty = max(notional / price, 0.001)
    # Round for typical Bybit linear qty precision.
    if symbol.upper().startswith("BTC"):
        return f"{qty:.3f}"
    if symbol.upper().startswith("ETH"):
        return f"{qty:.2f}"
    return f"{qty:.2f}"


def create_live_proposal_from_analysis(
    analysis: dict[str, Any],
    *,
    ttl_ms: int = _DEFAULT_TTL_MS,
    qty: str | None = None,
) -> dict[str, Any]:
    from apps.api.app.exchange.bybit_live_adapter import live_mutate_allowed

    plan = build_trade_plan_from_analysis(analysis)
    now_ms = int(time.time() * 1000)
    proposal_id = _new_id()
    armed = live_mutate_allowed()
    actionable = bool(plan["actionable"] and plan["side"] in {"BUY", "SELL"} and armed)
    resolved_qty = str(qty or _default_qty(plan["symbol"], plan.get("entry")))

    proposal = LiveTradeProposal(
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
        qty=resolved_qty,
        created_ms=now_ms,
        expires_ms=now_ms + int(ttl_ms),
        status="pending" if actionable else "failed",
        decision_public=plan.get("decision") or {},
        fail_reason=None if actionable else ("live_gates_off" if not armed else "signal_not_actionable"),
    )

    awaiting = False
    lines = [
        f"MAINNET LIVE trade plan for {plan['symbol']} {plan['category']} {plan['interval']}m.",
        plan["timing"] or f"Timing: confirm on closed {plan['interval']}m candles.",
        f"Last price: {plan['last_price']}.",
        f"Decision: {plan['analysis_action']}.",
        f"Risk verdict: {plan['risk_verdict'] or 'UNKNOWN'}.",
        *plan["level_lines"],
        f"Proposed qty: {resolved_qty}.",
    ]
    if plan["explanation"]:
        lines.append(plan["explanation"])

    if not armed:
        lines.append(
            "LIVE gates are off (AGENT_ALLOW_LIVE / MAINNET_TRADING_ENABLED / Bybit mainnet). "
            "No live proposal can be approved."
        )
    elif actionable:
        with _LOCK:
            _expire_locked(now_ms)
            _PROPOSALS[proposal_id] = proposal
        awaiting = True
        lines.append(
            f"REAL-MONEY Bybit MAINNET order ready — explicit chat Approve required. "
            f"Proposal id: {proposal_id}."
        )
        lines.append('Reply "Approve live trade" or "Reject live trade".')
        lines.append("Nothing is sent to Bybit until you Approve.")
    else:
        lines.append("No actionable BUY/SELL for live — HOLD/BLOCKED. No live order can be approved.")

    return {
        **plan,
        **analysis,
        "proposal_id": proposal_id if awaiting else None,
        "awaiting_human_approval": awaiting,
        "human_approval_required": awaiting,
        "qty": resolved_qty,
        "live_placeable": actionable,
        "summary": "\n".join(lines),
        "execution_mode": "LIVE",
        "live_orders": True,
        "execution_allowed": False,
        "exchange_order_sent": False,
    }


def propose_live_trade(
    *,
    symbol: str,
    category: str = "linear",
    interval: str = "15",
    candles: list[Candle],
    now_ms: int | None = None,
    qty: str | None = None,
) -> dict[str, Any]:
    analysis = run_full_analysis(
        symbol=symbol,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=now_ms,
        data_path="orchestrator_propose_live",
    )
    return create_live_proposal_from_analysis(analysis, qty=qty)


def create_manual_live_proposal(
    *,
    symbol: str,
    category: str = "linear",
    side: str,
    order_type: str = "Market",
    qty: str,
    leverage: int = 1,
    limit_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Build a pending LIVE open proposal from gathered futures intake fields."""
    from apps.api.app.exchange.bybit_live_adapter import live_mutate_allowed

    sym = str(symbol or "HYPEUSDT").upper()
    action = str(side or "").upper()
    if action in {"LONG", "BUY"}:
        action = "BUY"
    elif action in {"SHORT", "SELL"}:
        action = "SELL"
    else:
        return {
            "ok": False,
            "summary": f"Invalid side {side!r}. Use Buy or Sell.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    otype = "Limit" if str(order_type).lower().startswith("lim") else "Market"
    if otype == "Limit" and limit_price is None:
        return {
            "ok": False,
            "summary": "Limit orders require a limit price.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    armed = live_mutate_allowed()
    if not armed:
        return {
            "ok": False,
            "summary": "LIVE gates off — cannot create a Bybit futures proposal.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    now_ms = int(time.time() * 1000)
    proposal_id = _new_id()
    lev = max(1, min(50, int(leverage or 1)))
    proposal = LiveTradeProposal(
        proposal_id=proposal_id,
        symbol=sym,
        category=category or "linear",
        interval="15",
        side=action,
        entry=float(limit_price) if limit_price is not None else None,
        stop_loss=float(stop_loss) if stop_loss is not None else None,
        take_profit=float(take_profit) if take_profit is not None else None,
        last_price=None,
        risk_verdict="INTAKE",
        analysis_action=action,
        timing="Manual futures intake — human Approve required.",
        explanation=(
            f"Gathered: {otype} {action} qty={qty} leverage={lev}x"
            + (f" price={limit_price}" if limit_price is not None else "")
        ),
        qty=str(qty),
        created_ms=now_ms,
        expires_ms=now_ms + _DEFAULT_TTL_MS,
        status="pending",
        intent="open",
        order_type=otype,
        leverage=lev,
        limit_price=float(limit_price) if limit_price is not None else None,
    )
    with _LOCK:
        _expire_locked(now_ms)
        _PROPOSALS[proposal_id] = proposal

    lines = [
        f"Ready to open a live {sym} futures order.",
        f"{action} · {otype} · qty {qty} · {lev}x leverage.",
    ]
    if otype == "Limit":
        lines.append(f"Limit price {limit_price}.")
    lines.append(f"Stop loss: {stop_loss if stop_loss is not None else 'none'}.")
    lines.append(f"Take profit: {take_profit if take_profit is not None else 'none'}.")
    lines.append('Reply "Approve live trade" to send this to Bybit, or "Reject live trade".')
    lines.append("This uses real money — nothing is sent until you Approve.")
    if sym == "HYPEUSDT":
        lines.append(
            "Note: Bybit ErrCode 10029 blocks HYPEUSDT until that symbol is allowed on your API key."
        )
    return {
        "ok": True,
        "proposal_id": proposal_id,
        "symbol": sym,
        "side": action,
        "order_type": otype,
        "qty": str(qty),
        "leverage": lev,
        "limit_price": limit_price,
        "entry": limit_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "intent": "open",
        "awaiting_human_approval": True,
        "human_approval_required": True,
        "execution_mode": "LIVE",
        "live_orders": True,
        "execution_allowed": False,
        "exchange_order_sent": False,
        "summary": "\n".join(lines),
    }


def _bybit_error_help(exc: Any) -> str:
    """Map common Bybit API errors to operator actions (account/API key, not chat)."""
    text = str(getattr(exc, "reason", exc) or exc)
    if "10029" in text or "not whitelisted" in text.lower():
        return (
            f"{text}\n"
            "Bybit API key blocks this symbol (ErrCode 10029).\n"
            "Fix in Bybit → Account → API → edit this key:\n"
            "1) Enable Contract/USDT Perpetual trade permission.\n"
            "2) Turn OFF symbol whitelist, OR add HYPEUSDT to the allowed list.\n"
            "3) Save, then Approve the close again in Orchestrator.\n"
            "You can also close the short manually in the Bybit app until the key is fixed."
        )
    if "10005" in text or "permission" in text.lower():
        return (
            f"{text}\n"
            "API key lacks trade permission. Enable Orders/Positions write on this key."
        )
    return text


def _active_position(rows: list[Any]) -> dict[str, Any] | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            size = float(row.get("size") or row.get("positionQty") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if abs(size) > 0:
            return row
    return None


def list_live_positions(*, symbol: str = "HYPEUSDT", category: str = "linear") -> dict[str, Any]:
    """Read MAINNET Bybit positions (and open orders) — no mutate."""
    from apps.api.app.exchange.bybit_live_adapter import (
        LiveExecutionDisabled,
        get_default_live_adapter,
        live_mutate_allowed,
    )

    sym = str(symbol or "HYPEUSDT").upper()
    if not live_mutate_allowed():
        return {
            "ok": False,
            "symbol": sym,
            "positions": [],
            "open_orders": [],
            "summary": (
                f"LIVE gates off — cannot read Bybit positions for {sym}.\n"
                "Set AGENT_ALLOW_LIVE + MAINNET_TRADING_ENABLED on mainnet."
            ),
            "live_orders": True,
            "exchange_order_sent": False,
        }
    adapter = get_default_live_adapter()
    try:
        pos = adapter.fetch_positions(sym)
        orders = adapter.get_order_status(symbol=sym, category=category)
    except LiveExecutionDisabled as exc:
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Bybit position read refused: {getattr(exc, 'reason', exc)}",
            "live_orders": True,
            "exchange_order_sent": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Bybit position read failed: {type(exc).__name__}",
            "live_orders": True,
            "exchange_order_sent": False,
        }
    rows = list(pos.get("positions") or [])
    active = _active_position(rows)
    open_order = orders.get("order") if isinstance(orders, dict) else None
    open_orders = [open_order] if isinstance(open_order, dict) else []
    lines = [f"Bybit MAINNET snapshot for {sym} ({category})."]
    if active:
        size = active.get("size") or active.get("positionQty")
        side = active.get("side") or "?"
        avg = active.get("avgPrice") or active.get("entryPrice")
        lines.append(f"Open position: side={side} size={size} avg={avg}.")
        lines.append('To close: say "Close HYPEUSDT on Bybit" then Approve live trade.')
    else:
        lines.append("No open position size.")
    if open_orders:
        oid = open_orders[0].get("orderId") or open_orders[0].get("orderLinkId")
        lines.append(f"Open order present: {oid}.")
        lines.append('To cancel resting orders: say "Cancel open HYPEUSDT orders on Bybit".')
    else:
        lines.append("No resting open order returned for this symbol.")
    return {
        "ok": True,
        "symbol": sym,
        "category": category,
        "positions": rows,
        "active_position": active,
        "open_orders": open_orders,
        "summary": "\n".join(lines),
        "execution_mode": "LIVE",
        "live_orders": True,
        "exchange_order_sent": False,
        "awaiting_human_approval": False,
    }


def propose_live_close(
    *,
    symbol: str,
    category: str = "linear",
) -> dict[str, Any]:
    """Propose a reduce-only market close for the current Bybit position (Approve required)."""
    from apps.api.app.exchange.bybit_live_adapter import (
        LiveExecutionDisabled,
        get_default_live_adapter,
        live_mutate_allowed,
    )

    sym = str(symbol or "HYPEUSDT").upper()
    if not live_mutate_allowed():
        return {
            "ok": False,
            "symbol": sym,
            "summary": "LIVE gates off — cannot propose a Bybit close.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    adapter = get_default_live_adapter()
    try:
        pos = adapter.fetch_positions(sym)
    except LiveExecutionDisabled as exc:
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Cannot read Bybit position: {getattr(exc, 'reason', exc)}",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Cannot read Bybit position: {type(exc).__name__}",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }

    active = _active_position(list(pos.get("positions") or []))
    if active is None:
        # Fall back: propose cancelling resting orders if any.
        try:
            orders = adapter.get_order_status(symbol=sym, category=category)
        except Exception:  # noqa: BLE001
            orders = {}
        open_order = orders.get("order") if isinstance(orders, dict) else None
        if isinstance(open_order, dict) and (open_order.get("orderId") or open_order.get("orderLinkId")):
            return propose_live_cancel_orders(symbol=sym, category=category)
        return {
            "ok": False,
            "symbol": sym,
            "summary": (
                f"No open Bybit position (and no resting order) for {sym}.\n"
                "Nothing to close. Check Bybit or ask list_live_positions."
            ),
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }

    try:
        size = abs(float(active.get("size") or active.get("positionQty") or 0))
    except (TypeError, ValueError):
        size = 0.0
    if size <= 0:
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Position size is zero for {sym}. Nothing to close.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }

    pos_side = str(active.get("side") or "").strip()
    # Bybit: Buy/Sell on position. Close with opposite market + reduceOnly.
    if pos_side.lower() in {"buy", "long"}:
        close_side = "Sell"
        analysis_action = "SELL"
    else:
        close_side = "Buy"
        analysis_action = "BUY"

    qty = str(active.get("size") or size)
    avg = active.get("avgPrice") or active.get("entryPrice")
    now_ms = int(time.time() * 1000)
    proposal_id = _new_id()
    proposal = LiveTradeProposal(
        proposal_id=proposal_id,
        symbol=sym,
        category=category,
        interval="15",
        side=analysis_action,
        entry=float(avg) if avg not in (None, "") else None,
        stop_loss=None,
        take_profit=None,
        last_price=None,
        risk_verdict="CLOSE",
        analysis_action=analysis_action,
        timing="Immediate market close of current Bybit position.",
        explanation=f"Close {pos_side} position size={qty} via {close_side} market reduceOnly.",
        qty=qty,
        created_ms=now_ms,
        expires_ms=now_ms + _DEFAULT_TTL_MS,
        status="pending",
        intent="close",
        reduce_only=True,
        position_side=pos_side,
    )
    with _LOCK:
        _expire_locked(now_ms)
        _PROPOSALS[proposal_id] = proposal

    lines = [
        f"Ready to close your live {sym} position.",
        f"Open now: {pos_side} {qty} (avg {avg}).",
        f"Close with a {close_side} market order for {qty} (reduce-only).",
        "Tap Approve below to close on Bybit, or Deny to keep it open.",
        "This uses real money — nothing is sent until you Approve.",
    ]
    return {
        "ok": True,
        "proposal_id": proposal_id,
        "symbol": sym,
        "category": category,
        "side": analysis_action,
        "close_side": close_side,
        "qty": qty,
        "entry": proposal.entry,
        "position_side": pos_side,
        "intent": "close",
        "reduce_only": True,
        "awaiting_human_approval": True,
        "human_approval_required": True,
        "execution_mode": "LIVE",
        "live_orders": True,
        "execution_allowed": False,
        "exchange_order_sent": False,
        "summary": "\n".join(lines),
    }


def propose_live_cancel_orders(
    *,
    symbol: str,
    category: str = "linear",
) -> dict[str, Any]:
    """Propose cancelling resting Bybit open orders for a symbol (Approve required).

    If a position is open (not a resting order), redirect to propose_live_close —
    cancel_order cannot flatten a position.
    """
    from apps.api.app.exchange.bybit_live_adapter import (
        LiveExecutionDisabled,
        get_default_live_adapter,
        live_mutate_allowed,
    )

    sym = str(symbol or "HYPEUSDT").upper()
    if not live_mutate_allowed():
        return {
            "ok": False,
            "symbol": sym,
            "summary": "LIVE gates off — cannot propose Bybit cancel.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    adapter = get_default_live_adapter()
    # Position ≠ resting order. Prefer close when size > 0.
    try:
        pos = adapter.fetch_positions(sym)
        active = _active_position(list(pos.get("positions") or []))
        if active is not None:
            body = propose_live_close(symbol=sym, category=category)
            note = (
                "You asked to cancel, but Bybit shows an OPEN POSITION (not a resting order). "
                "Prepared a CLOSE (reduceOnly market) proposal instead — Approve to flatten."
            )
            body["summary"] = note + "\n" + str(body.get("summary") or "")
            return body
    except Exception:  # noqa: BLE001 — fall through to resting-order path
        pass
    try:
        orders = adapter.get_order_status(symbol=sym, category=category)
    except LiveExecutionDisabled as exc:
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Cannot read open orders: {getattr(exc, 'reason', exc)}",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Cannot read open orders: {type(exc).__name__}",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    open_rows = list(orders.get("orders") or []) if isinstance(orders, dict) else []
    open_order = open_rows[0] if open_rows else (orders.get("order") if isinstance(orders, dict) else None)
    if not isinstance(open_order, dict):
        return {
            "ok": False,
            "symbol": sym,
            "summary": (
                f"No resting open order found for {sym}.\n"
                "If you have a POSITION (size > 0), say: Close HYPEUSDT on Bybit."
            ),
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    oid = str(open_order.get("orderId") or "")
    link = str(open_order.get("orderLinkId") or "")
    if not oid and not link:
        return {
            "ok": False,
            "symbol": sym,
            "summary": f"Open order payload missing ids for {sym}.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    now_ms = int(time.time() * 1000)
    proposal_id = _new_id()
    proposal = LiveTradeProposal(
        proposal_id=proposal_id,
        symbol=sym,
        category=category,
        interval="15",
        side="CANCEL",
        entry=None,
        stop_loss=None,
        take_profit=None,
        last_price=None,
        risk_verdict="CANCEL",
        analysis_action="CANCEL",
        timing="Cancel resting Bybit open order.",
        explanation=f"Cancel orderId={oid or 'n/a'} orderLinkId={link or 'n/a'}.",
        qty="0",
        created_ms=now_ms,
        expires_ms=now_ms + _DEFAULT_TTL_MS,
        status="pending",
        intent="cancel_orders",
        reduce_only=False,
        open_order_ids=[x for x in (oid, link) if x],
    )
    with _LOCK:
        _expire_locked(now_ms)
        _PROPOSALS[proposal_id] = proposal
    lines = [
        f"MAINNET LIVE CANCEL proposal for {sym}.",
        f"Order id: {oid or 'n/a'}. Link: {link or 'n/a'}.",
        f"Proposal id: {proposal_id}.",
        'Reply "Approve live trade" to cancel on Bybit, or "Reject live trade".',
    ]
    return {
        "ok": True,
        "proposal_id": proposal_id,
        "symbol": sym,
        "intent": "cancel_orders",
        "awaiting_human_approval": True,
        "human_approval_required": True,
        "execution_mode": "LIVE",
        "live_orders": True,
        "exchange_order_sent": False,
        "summary": "\n".join(lines),
    }


def reject_live_trade(proposal_id: str = "") -> dict[str, Any]:
    proposal = get_live_proposal(proposal_id)
    if proposal is None:
        proposal = latest_pending_live_proposal()
    if proposal is None:
        return {
            "ok": False,
            "summary": "No pending LIVE trade proposal to reject.",
            "live_orders": True,
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
                "live_orders": True,
                "awaiting_human_approval": False,
            }
        proposal.status = "rejected"
    return {
        "ok": True,
        "proposal_id": proposal.proposal_id,
        "status": "rejected",
        "symbol": proposal.symbol,
        "side": proposal.side,
        "summary": (
            f"LIVE trade proposal {proposal.proposal_id} rejected.\n"
            "No Bybit order was sent."
        ),
        "execution_mode": "LIVE",
        "live_orders": True,
        "exchange_order_sent": False,
        "awaiting_human_approval": False,
    }


def approve_live_trade(
    proposal_id: str | None = None,
    *,
    candles: list[Candle] | None = None,
) -> dict[str, Any]:
    """Place a MAINNET Bybit order after explicit human Approve in chat."""
    from apps.api.app.exchange.bybit_live_adapter import (
        LiveExecutionDisabled,
        get_default_live_adapter,
        live_mutate_allowed,
    )

    proposal = get_live_proposal(proposal_id or "")
    if proposal is None:
        proposal = latest_pending_live_proposal()
    if proposal is None:
        # If checklist is still open, guide the user instead of a dead-end "no proposal".
        try:
            from agent.orchestrator.futures_intake import continue_futures_intake, get_active_intake

            if get_active_intake() is not None:
                body = continue_futures_intake("")
                summary = str(body.get("summary") or "")
                return {
                    **body,
                    "ok": False,
                    "summary": (
                        "Checklist is not finished yet — I can’t Approve until the proposal is ready.\n\n"
                        + summary
                    ),
                }
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False,
            "summary": (
                "No pending LIVE trade proposal yet.\n"
                'Say "Place futures order HYPEUSDT" (or BTCUSDT), fill the checklist '
                "(side, Market/Limit, qty, leverage, SL/TP), then reply "
                '"Approve live trade".'
            ),
            "live_orders": True,
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
            "summary": f"Proposal {proposal.proposal_id} is {proposal.status}. Run a new live trade plan.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }

    if not live_mutate_allowed():
        with _LOCK:
            proposal.status = "failed"
            proposal.fail_reason = "live_gates_off"
        return {
            "ok": False,
            "proposal_id": proposal.proposal_id,
            "summary": "LIVE gates are off — Bybit order was NOT sent.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }

    adapter = get_default_live_adapter()
    intent = str(proposal.intent or "open").lower()

    # Cancel resting orders — no candle/risk re-check.
    if intent == "cancel_orders":
        try:
            cancel_kwargs: dict[str, Any] = {"symbol": proposal.symbol, "category": proposal.category}
            for item in proposal.open_order_ids:
                text = str(item)
                if text.startswith("cnlive_") or text.startswith("ltp_"):
                    cancel_kwargs["orderLinkId"] = text
                else:
                    cancel_kwargs["orderId"] = text
            cancelled = adapter.cancel_order(**cancel_kwargs)
        except LiveExecutionDisabled as exc:
            with _LOCK:
                proposal.status = "failed"
                proposal.fail_reason = str(getattr(exc, "reason", exc))
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "summary": f"Bybit cancel refused: {getattr(exc, 'reason', exc)}",
                "live_orders": True,
                "exchange_order_sent": False,
                "awaiting_human_approval": False,
            }
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                proposal.status = "failed"
                proposal.fail_reason = type(exc).__name__
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "summary": f"Bybit cancel failed: {type(exc).__name__}",
                "live_orders": True,
                "exchange_order_sent": False,
                "awaiting_human_approval": False,
            }
        with _LOCK:
            proposal.status = "approved"
        # Re-check: cancel does not flatten positions.
        still_open = ""
        try:
            pos = adapter.fetch_positions(proposal.symbol)
            active = _active_position(list(pos.get("positions") or []))
            if active is not None:
                still_open = (
                    f"\nNOTE: Position still open (side={active.get('side')} "
                    f"size={active.get('size')}). Cancel only removes resting orders. "
                    'Say "Close HYPEUSDT on Bybit" then Approve to flatten.'
                )
        except Exception:  # noqa: BLE001
            still_open = ""
        return {
            "ok": True,
            "proposal_id": proposal.proposal_id,
            "status": "approved",
            "intent": "cancel_orders",
            "symbol": proposal.symbol,
            "live": cancelled,
            "awaiting_human_approval": False,
            "execution_mode": "LIVE",
            "live_orders": True,
            "execution_allowed": True,
            "exchange_order_sent": True,
            "summary": (
                f"Cancel sent for {proposal.symbol}. Check Bybit to confirm."
                + still_open
            ),
        }

    # Close position — reduce-only market; skip signal re-check (HOLD must not block exit).
    if intent == "close":
        side = "Sell" if str(proposal.analysis_action).upper() == "SELL" else "Buy"
        # Fresh size from exchange in case position changed since propose.
        qty = proposal.qty
        position_idx = 0
        try:
            pos = adapter.fetch_positions(proposal.symbol)
            active = _active_position(list(pos.get("positions") or []))
            if active is None:
                with _LOCK:
                    proposal.status = "failed"
                    proposal.fail_reason = "already_flat"
                return {
                    "ok": False,
                    "proposal_id": proposal.proposal_id,
                    "summary": f"No open Bybit position for {proposal.symbol} — already flat.",
                    "live_orders": True,
                    "exchange_order_sent": False,
                    "awaiting_human_approval": False,
                }
            qty = str(active.get("size") or qty)
            try:
                position_idx = int(active.get("positionIdx") or 0)
            except (TypeError, ValueError):
                position_idx = 0
            pos_side = str(active.get("side") or "")
            side = "Sell" if pos_side.lower() in {"buy", "long"} else "Buy"
        except Exception:  # noqa: BLE001 — use proposal snapshot
            pass
        try:
            placed = adapter.place_order(
                symbol=proposal.symbol,
                side=side,
                orderType="Market",
                qty=qty,
                category=proposal.category,
                reduceOnly=True,
                positionIdx=position_idx,
                timeInForce="IOC",
                intent_key=proposal.proposal_id,
                orderLinkId=proposal.proposal_id.replace("ltp_", "cnlive_")[:36],
            )
        except LiveExecutionDisabled as exc:
            with _LOCK:
                proposal.status = "failed"
                proposal.fail_reason = str(getattr(exc, "reason", exc))
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "summary": f"Couldn’t close on Bybit:\n{_bybit_error_help(exc)}",
                "live_orders": True,
                "exchange_order_sent": False,
                "awaiting_human_approval": False,
                "bybit_error": str(getattr(exc, "reason", exc)),
            }
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                proposal.status = "failed"
                proposal.fail_reason = f"{type(exc).__name__}:{exc}"
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "summary": f"Close failed:\n{_bybit_error_help(exc)}",
                "live_orders": True,
                "exchange_order_sent": False,
                "awaiting_human_approval": False,
            }
        with _LOCK:
            proposal.status = "approved"
            proposal.exchange_order_id = str(placed.get("exchange_order_id") or "")
            proposal.client_order_id = str(placed.get("client_order_id") or "")
        return {
            "ok": True,
            "proposal_id": proposal.proposal_id,
            "status": "approved",
            "intent": "close",
            "symbol": proposal.symbol,
            "side": proposal.analysis_action,
            "qty": qty,
            "exchange_order_id": proposal.exchange_order_id,
            "client_order_id": proposal.client_order_id,
            "live": placed,
            "awaiting_human_approval": False,
            "execution_mode": "LIVE",
            "live_orders": True,
            "execution_allowed": True,
            "exchange_order_sent": True,
            "summary": (
                f"Close order sent for {proposal.symbol}.\n"
                f"{side} market · qty {qty}.\n"
                f"Bybit order id: {proposal.exchange_order_id or 'pending'}.\n"
                "Please confirm the position is flat in the Bybit app."
            ),
        }

    # Manual futures intake: use gathered side/type/leverage (no signal re-check).
    intake_open = str(proposal.risk_verdict or "").upper() == "INTAKE" or proposal.leverage is not None
    if intake_open:
        action = str(proposal.analysis_action or proposal.side or "").upper()
        if action not in {"BUY", "SELL"}:
            with _LOCK:
                proposal.status = "failed"
                proposal.fail_reason = "invalid_side"
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "summary": "Invalid side on intake proposal.",
                "live_orders": True,
                "exchange_order_sent": False,
                "awaiting_human_approval": False,
            }
        side = "Buy" if action == "BUY" else "Sell"
        otype = str(proposal.order_type or "Market")
        if proposal.leverage:
            try:
                adapter.set_leverage(symbol=proposal.symbol, leverage=int(proposal.leverage))
            except LiveExecutionDisabled as exc:
                with _LOCK:
                    proposal.status = "failed"
                    proposal.fail_reason = str(getattr(exc, "reason", exc))
                return {
                    "ok": False,
                    "proposal_id": proposal.proposal_id,
                    "summary": f"Bybit set leverage refused:\n{_bybit_error_help(exc)}",
                    "live_orders": True,
                    "exchange_order_sent": False,
                    "awaiting_human_approval": False,
                }
            except Exception as exc:  # noqa: BLE001
                with _LOCK:
                    proposal.status = "failed"
                    proposal.fail_reason = type(exc).__name__
                return {
                    "ok": False,
                    "proposal_id": proposal.proposal_id,
                    "summary": f"Bybit set leverage failed: {exc}",
                    "live_orders": True,
                    "exchange_order_sent": False,
                    "awaiting_human_approval": False,
                }
        # Re-normalize qty / prices to Bybit lot + tick (prevents ErrCode 10001 Qty invalid).
        from agent.orchestrator.symbol_rules import (
            fetch_instrument_public,
            normalize_price,
            normalize_qty,
        )

        instrument = None
        try:
            fetched = adapter.fetch_instrument(proposal.symbol)
            instrument = fetched.get("instrument") if isinstance(fetched, dict) else None
        except Exception:  # noqa: BLE001
            instrument = fetch_instrument_public(proposal.symbol, proposal.category)
        qty = normalize_qty(
            proposal.symbol,
            proposal.qty,
            price=proposal.limit_price or proposal.entry or proposal.last_price,
            instrument=instrument if isinstance(instrument, dict) else None,
        ) or str(proposal.qty)
        proposal.qty = qty
        if proposal.stop_loss is not None:
            sl = normalize_price(
                proposal.symbol,
                proposal.stop_loss,
                instrument=instrument if isinstance(instrument, dict) else None,
            )
            if sl is not None:
                proposal.stop_loss = float(sl)
        if proposal.take_profit is not None:
            tp = normalize_price(
                proposal.symbol,
                proposal.take_profit,
                instrument=instrument if isinstance(instrument, dict) else None,
            )
            if tp is not None:
                proposal.take_profit = float(tp)
        if proposal.limit_price is not None:
            lp = normalize_price(
                proposal.symbol,
                proposal.limit_price,
                instrument=instrument if isinstance(instrument, dict) else None,
            )
            if lp is not None:
                proposal.limit_price = float(lp)

        place_kwargs: dict[str, Any] = {
            "symbol": proposal.symbol,
            "side": side,
            "orderType": otype,
            "qty": qty,
            "category": proposal.category,
            "positionIdx": 0,
            "intent_key": proposal.proposal_id,
            "orderLinkId": proposal.proposal_id.replace("ltp_", "cnlive_")[:36],
        }
        if otype == "Limit":
            place_kwargs["price"] = proposal.limit_price if proposal.limit_price is not None else proposal.entry
            place_kwargs["timeInForce"] = "GTC"
        else:
            place_kwargs["timeInForce"] = "IOC"
        if proposal.stop_loss is not None:
            place_kwargs["stopLoss"] = str(proposal.stop_loss)
        if proposal.take_profit is not None:
            place_kwargs["takeProfit"] = str(proposal.take_profit)
        try:
            placed = adapter.place_order(**place_kwargs)
        except LiveExecutionDisabled as exc:
            with _LOCK:
                proposal.status = "failed"
                proposal.fail_reason = str(getattr(exc, "reason", exc))
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "summary": f"Bybit LIVE order refused:\n{_bybit_error_help(exc)}",
                "live_orders": True,
                "exchange_order_sent": False,
                "awaiting_human_approval": False,
            }
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                proposal.status = "failed"
                proposal.fail_reason = type(exc).__name__
            return {
                "ok": False,
                "proposal_id": proposal.proposal_id,
                "summary": f"Bybit LIVE order failed:\n{_bybit_error_help(exc)}",
                "live_orders": True,
                "exchange_order_sent": False,
                "awaiting_human_approval": False,
            }
        with _LOCK:
            proposal.status = "approved"
            proposal.exchange_order_id = str(placed.get("exchange_order_id") or "")
            proposal.client_order_id = str(placed.get("client_order_id") or "")
        return {
            "ok": True,
            "proposal_id": proposal.proposal_id,
            "status": "approved",
            "symbol": proposal.symbol,
            "side": action,
            "order_type": otype,
            "qty": proposal.qty,
            "leverage": proposal.leverage,
            "entry": proposal.entry,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "exchange_order_id": proposal.exchange_order_id,
            "client_order_id": proposal.client_order_id,
            "live": placed,
            "awaiting_human_approval": False,
            "execution_mode": "LIVE",
            "live_orders": True,
            "execution_allowed": True,
            "exchange_order_sent": True,
            "summary": (
                f"Human-approved MAINNET FUTURES order for {proposal.proposal_id}.\n"
                f"Symbol: {proposal.symbol}. Side: {side}. Type: {otype}. Qty: {proposal.qty}. "
                f"Leverage: {proposal.leverage or 1}x.\n"
                f"Exchange order id: {proposal.exchange_order_id or 'n/a'}.\n"
                "REAL MONEY — verify position on Bybit."
            ),
        }

    if candles is None or len(candles) < 2:
        return {
            "ok": False,
            "proposal_id": proposal.proposal_id,
            "summary": "Public candles unavailable — live order not sent. Proposal still pending.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": True,
        }

    # Signal-based open: re-evaluate risk on fresh candles before any exchange call.
    pipe = SignalPipeline(config=SignalPipelineConfig(), persist=False)
    decision = pipe.evaluate(
        symbol=proposal.symbol,
        category=proposal.category,
        interval=proposal.interval,
        candles=candles,
        now_ms=now_ms,
        data_path="orchestrator_approve_live",
        news_advisory_enabled=news_advisory_enabled_from_env(),
    )
    action = decision.action.value if hasattr(decision.action, "value") else str(decision.action)
    verdict = decision.risk.verdict.value if hasattr(decision.risk.verdict, "value") else str(decision.risk.verdict)

    if str(verdict).upper() != "APPROVED" or str(action).upper() not in {"BUY", "SELL"}:
        with _LOCK:
            proposal.status = "failed"
            proposal.fail_reason = f"recheck_{action}_{verdict}"
        return {
            "ok": False,
            "proposal_id": proposal.proposal_id,
            "status": "failed",
            "risk_verdict": verdict,
            "analysis_action": action,
            "summary": (
                f"Live approve aborted after re-check: action={action} risk={verdict}.\n"
                "No Bybit order was sent."
            ),
            "execution_mode": "LIVE",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }

    side = "Buy" if str(action).upper() == "BUY" else "Sell"
    try:
        placed = adapter.place_order(
            symbol=proposal.symbol,
            side=side,
            orderType="Market",
            qty=proposal.qty,
            category=proposal.category,
            stopLoss=proposal.stop_loss,
            takeProfit=proposal.take_profit,
            timeInForce="IOC",
            positionIdx=0,
            intent_key=proposal.proposal_id,
            orderLinkId=proposal.proposal_id.replace("ltp_", "cnlive_")[:36],
        )
    except LiveExecutionDisabled as exc:
        with _LOCK:
            proposal.status = "failed"
            proposal.fail_reason = str(getattr(exc, "reason", exc))
        return {
            "ok": False,
            "proposal_id": proposal.proposal_id,
            "status": "failed",
            "summary": f"Bybit LIVE order refused:\n{_bybit_error_help(exc)}",
            "execution_mode": "LIVE",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }
    except Exception as exc:  # noqa: BLE001
        with _LOCK:
            proposal.status = "failed"
            proposal.fail_reason = type(exc).__name__
        return {
            "ok": False,
            "proposal_id": proposal.proposal_id,
            "status": "failed",
            "summary": f"Bybit LIVE order failed:\n{_bybit_error_help(exc)}",
            "execution_mode": "LIVE",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }

    with _LOCK:
        proposal.status = "approved"
        proposal.exchange_order_id = str(placed.get("exchange_order_id") or "")
        proposal.client_order_id = str(placed.get("client_order_id") or "")

    lines = [
        f"Human-approved MAINNET LIVE execution for proposal {proposal.proposal_id}.",
        f"Symbol: {proposal.symbol}. Side: {side}. Qty: {proposal.qty}.",
        f"Re-check action: {action}. Risk: {verdict}.",
        f"Entry: {proposal.entry}. SL: {proposal.stop_loss}. TP: {proposal.take_profit}.",
        f"Exchange order id: {proposal.exchange_order_id or 'n/a'}.",
        f"Client order id: {proposal.client_order_id or 'n/a'}.",
        "REAL MONEY — verify position on Bybit.",
    ]
    return {
        "ok": True,
        "proposal_id": proposal.proposal_id,
        "status": "approved",
        "symbol": proposal.symbol,
        "side": action,
        "qty": proposal.qty,
        "entry": proposal.entry,
        "stop_loss": proposal.stop_loss,
        "take_profit": proposal.take_profit,
        "risk_verdict": verdict,
        "analysis_action": action,
        "exchange_order_id": proposal.exchange_order_id,
        "client_order_id": proposal.client_order_id,
        "live": placed,
        "awaiting_human_approval": False,
        "execution_mode": "LIVE",
        "live_orders": True,
        "execution_allowed": True,
        "exchange_order_sent": True,
        "summary": "\n".join(lines),
    }
