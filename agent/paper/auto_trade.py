"""Automatic paper execution after a multi-agent decision.

BUY opens a simulated long. SELL closes that long. HOLD, BLOCKED, and a risk
veto do not create an order. Fills happen on the next confirmed candle.

This never calls a private exchange API and never sets live execution.
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from decimal import Decimal
from typing import Any

from agent.backtest.execution_adapter import decision_to_backtest_signal, market_to_paper_candle
from agent.market_data import Candle
from agent.multi_agent.pipeline import SignalPipeline
from agent.paper.broker import BrokerResult, PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.models import OrderSide, PaperCandle, SessionStatus
from agent.paper.store import PaperStore

_REFUSED_NAMES = {"cryptonova_paper.sqlite3"}


class AutomaticPaperTrader:
    def __init__(
        self,
        journal_path: str | Path,
        config: PaperBrokerConfig | None = None,
        *,
        now_ms: int = 1,
        risk_fraction: Decimal | None = None,
    ) -> None:
        path = Path(journal_path)
        if path.name.lower() in _REFUSED_NAMES:
            raise RuntimeError("refusing_primary_paper_journal")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.journal_path = path
        self.store = PaperStore(path, isolated_sqlite=True)
        self.broker = PaperBroker(self.store, config or PaperBrokerConfig())
        self.session = self._resume_or_create(path, now_ms)
        self.live_orders = False
        self.risk_fraction = risk_fraction

    def _resume_or_create(self, path: Path, now_ms: int):
        marker = path.with_suffix(path.suffix + ".session")
        if marker.exists():
            existing = self.broker.get_session(marker.read_text(encoding="utf-8").strip())
            if existing is not None and existing.status is SessionStatus.ACTIVE:
                return existing
        created = self.broker.create_session(now_ms=now_ms)
        marker.write_text(created.session_id, encoding="utf-8")
        return created

    def apply_decision(self, decision: Any, candle: PaperCandle) -> dict[str, Any]:
        signal = decision_to_backtest_signal(decision, signal_candle_start_ms=candle.start_ms)
        if signal is None:
            fills = self._advance(candle)
            return self.snapshot(action="NONE", submit=None, fills=fills, reason="MISSING_DECISION")
        action = signal.action.upper()
        verdict = signal.risk_verdict.upper()
        if action not in {"BUY", "SELL"} or verdict != "APPROVED":
            fills = self._advance(candle)
            return self.snapshot(
                action=action,
                submit=None,
                fills=fills,
                reason="NOT_ACTIONABLE",
            )
        if action == "BUY" and self.risk_fraction is not None:
            signal = self._size_entry(signal)
            if signal is None:
                fills = self._advance(candle)
                return self.snapshot(action="HOLD", submit=None, fills=fills, reason="INVALID_ENTRY_RISK")
        submit = self.broker.submit_signal(session_id=self.session.session_id, signal=signal)
        fills = self._advance(candle, interval=signal.interval or "15")
        return self.snapshot(action=action, submit=submit, fills=fills, reason=submit.reason)

    def _size_entry(self, signal: PaperSignalInput) -> PaperSignalInput | None:
        """Enforce the authorized stop-loss budget independently of agent output."""
        entry, stop, target = signal.entry_price, signal.stop_loss, signal.take_profit
        values = (entry, stop, target, signal.position_notional)
        if any(value is None or not value.is_finite() or value <= 0 for value in values):
            return None
        if not stop < entry < target:
            return None
        session = self.broker.get_session(self.session.session_id)
        if session is None:
            return None
        positions = self.store.get_open_positions(session.session_id)
        equity = session.available_balance + session.reserved_capital + sum(
            (position.unrealized_pnl for position in positions), Decimal("0")
        )
        # Reserve fees and adverse slippage at entry and stop. Gaps can still exceed
        # this planned loss; this is a deterministic size bound, not a loss guarantee.
        costs = self.broker.config.fee_rate * 2 + self.broker.config.slippage_bps / Decimal("5000")
        loss_fraction = (entry - stop) / entry + costs
        cash_cost = (Decimal("1") + self.broker.config.fee_rate) * (
            Decimal("1") + self.broker.config.slippage_bps / Decimal("10000")
        )
        exposure = sum((position.entry_price * position.quantity for position in positions), Decimal("0"))
        capped = min(
            signal.position_notional,
            max(Decimal("0"), equity) * self.risk_fraction / loss_fraction,
            session.available_balance / cash_cost * Decimal("0.999"),
            max(Decimal("0"), self.broker.config.max_total_exposure - exposure),
        )
        return replace(signal, position_notional=capped) if capped > 0 else None

    def block_pending_entries(self, *, reason: str, now_ms: int) -> int:
        """Withdraw queued entries before protective candle processing can fill them."""
        pending = [order for order in self.store.list_pending_orders(self.session.session_id) if order.side is OrderSide.BUY]
        with self.store.transaction() as conn:
            for order in pending:
                self.store.update_order_rejected(conn, order_id=order.order_id, reason=reason)
                self.store.append_event(
                    conn, session_id=self.session.session_id, event_type="ENTRY_WITHDRAWN",
                    payload={"order_id": order.order_id, "reason": reason}, created_ms=now_ms,
                    idempotency_key=f"entry_withdrawn:{order.order_id}",
                )
        return len(pending)

    def request_close(self, candle: PaperCandle, *, now_ms: int) -> list[BrokerResult]:
        """Queue risk-reducing exits for the next confirmed candle, without look-ahead."""
        pending = self.store.list_pending_orders(self.session.session_id)
        results = []
        for position in self.store.get_open_positions(self.session.session_id):
            if position.symbol != candle.symbol or any(
                order.side is OrderSide.SELL and order.symbol == position.symbol for order in pending
            ):
                continue
            results.append(self.broker.submit_signal(
                session_id=self.session.session_id,
                signal=PaperSignalInput(
                    signal_id=f"supervisor-close:{position.position_id}", symbol=position.symbol,
                    category=position.category, action="SELL", risk_verdict="APPROVED",
                    entry_price=candle.close, stop_loss=None, take_profit=None, position_notional=None,
                    signal_candle_start_ms=candle.start_ms, created_ms=now_ms, interval=candle.interval,
                ),
            ))
        return results

    def _advance(self, candle: PaperCandle, interval: str = "15") -> list[BrokerResult]:
        return self.broker.process_candle(
            session_id=self.session.session_id,
            candle=candle,
            interval=candle.interval or interval,
        )

    def snapshot(
        self,
        *,
        action: str,
        submit: BrokerResult | None,
        fills: list[BrokerResult],
        reason: str,
    ) -> dict[str, Any]:
        session = self.broker.get_session(self.session.session_id)
        positions = self.store.get_open_positions(self.session.session_id)
        return {
            "mode": "PAPER_AUTOMATIC",
            "live_orders": False,
            "execution_allowed": False,
            "exchange_order_sent": False,
            "action": action,
            "reason": reason,
            "order_id": None if submit is None else submit.order_id,
            "fill_reasons": [item.reason for item in fills],
            "open_positions": len(positions),
            "position_qty": str(positions[0].quantity) if positions else "0",
            "available_balance": None if session is None else str(session.available_balance),
            "realized_pnl": None if session is None else str(session.realized_pnl),
            "session_id": self.session.session_id,
        }


def trade_after_analysis(
    trader: AutomaticPaperTrader,
    *,
    symbol: str,
    category: str,
    interval: str,
    candles: list[Candle],
    now_ms: int,
) -> dict[str, Any]:
    """Run the multi-agent analysis, then place the paper buy or sell."""
    decision = SignalPipeline(persist=False).evaluate(
        symbol=symbol,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=now_ms,
        data_path="paper_automatic",
    )
    if not candles:
        return trader.snapshot(action="NONE", submit=None, fills=[], reason="NO_CANDLES")
    result = trader.apply_decision(decision, market_to_paper_candle(candles[-1], symbol=symbol, interval=interval))
    result["analysis_action"] = decision.action.value
    result["risk_verdict"] = decision.risk.verdict.value
    result["execution_allowed"] = False
    result["live_orders"] = False
    return result
