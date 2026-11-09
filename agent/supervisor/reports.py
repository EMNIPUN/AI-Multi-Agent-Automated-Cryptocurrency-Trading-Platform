"""Read-only paper journal report. Simulated equity is never mixed with exchange equity."""

from __future__ import annotations

from decimal import Decimal
import json
from typing import Any

from agent.paper.auto_trade import AutomaticPaperTrader


def journal_report(trader: AutomaticPaperTrader) -> dict[str, Any]:
    session = trader.broker.get_session(trader.session.session_id)
    positions = trader.store.get_open_positions(trader.session.session_id)
    if session is None:
        return {
            "equity_source": "paper_journal",
            "exchange_equity_included": False,
            "available": False,
            "live_orders": False,
        }
    unrealized = sum((item.unrealized_pnl for item in positions), Decimal("0"))
    equity = session.available_balance + session.reserved_capital + unrealized
    drawdown = max(Decimal("0"), session.initial_balance - equity)
    events = trader.store.list_account_events(session.session_id)
    closed = []
    for event in events:
        if event["event_type"] == "POSITION_CLOSED":
            payload = json.loads(event["payload_json"])
            position = trader.store.get_position(payload.get("position_id", ""))
            if position is not None:
                closed.append(position)
    winning = sum(position.realized_pnl > 0 for position in closed)
    def position_dict(position):
        return {
            "position_id": position.position_id, "symbol": position.symbol, "category": position.category,
            "status": position.status.value, "quantity": str(position.quantity),
            "entry_price": str(position.entry_price),
            "mark_price": str(position.mark_price) if position.mark_price is not None else None,
            "stop_loss": str(position.stop_loss) if position.stop_loss is not None else None,
            "take_profit": str(position.take_profit) if position.take_profit is not None else None,
            "unrealized_pnl": str(position.unrealized_pnl), "realized_pnl": str(position.realized_pnl),
            "opened_ms": position.opened_ms, "closed_ms": position.closed_ms,
            "exit_price": str(position.exit_price) if position.exit_price is not None else None,
            "exit_reason": position.exit_reason,
        }
    return {
        "available": True,
        "equity_source": "paper_journal",
        "exchange_equity_included": False,
        "session_id": session.session_id,
        "currency": session.currency,
        "initial_balance": str(session.initial_balance),
        "available_balance": str(session.available_balance),
        "reserved_capital": str(session.reserved_capital),
        "realized_pnl": str(session.realized_pnl),
        "fees_paid": str(session.fees_paid),
        "open_positions": len(positions),
        "unrealized_pnl": str(unrealized),
        "equity": str(equity),
        "drawdown": str(drawdown),
        "positions": [position_dict(position) for position in positions],
        "recent_trades": [position_dict(position) for position in reversed(closed[-25:])],
        "recent_events": [
            {"event_id": event["event_id"], "event_type": event["event_type"],
             "created_ms": event["created_ms"], "payload": json.loads(event["payload_json"])}
            for event in reversed(events[-40:])
        ],
        "pending_orders": [
            {"order_id": order.order_id, "symbol": order.symbol, "side": order.side.value,
             "quantity": str(order.quantity), "status": order.status.value, "created_ms": order.created_ms}
            for order in trader.store.list_pending_orders(session.session_id)
        ],
        "closed_trades": len(closed),
        "winning_trades": winning,
        "win_rate": winning / len(closed) if closed else None,
        "protective_closes": [
            position_dict(position)
            for position in closed
            if str(position.exit_reason or "").upper() in {"STOP_LOSS", "TAKE_PROFIT", "SL", "TP"}
        ][-25:],
        "signal_closes": [
            position_dict(position)
            for position in closed
            if str(position.exit_reason or "").upper() in {"SIGNAL_SELL", "SELL", "MANUAL_CLOSE", "CLOSE"}
        ][-25:],
        "live_orders": False,
        "execution_allowed": False,
    }
