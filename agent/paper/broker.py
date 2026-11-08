"""Local paper trading broker — simulated only; never touches live execution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from agent.paper.accounting import (
    capital_to_reserve,
    long_net_pnl,
    long_unrealized_pnl,
    notional,
    q,
)
from agent.paper.config import PaperBrokerConfig, d
from agent.paper.fills import evaluate_long_exit, simulate_entry_fill
from agent.paper.models import (
    ExitReason,
    OrderSide,
    OrderStatus,
    PaperCandle,
    PaperFill,
    PaperOrder,
    PaperPosition,
    PaperSession,
    PositionStatus,
    SessionStatus,
)
from agent.paper.portfolio import apply_equity_and_limits, load_risk_state_view
from agent.paper.risk import (
    PortfolioRiskVerdict,
    ProposedEntry,
    evaluate_portfolio_entry,
    exit_allowed_while_halted,
)
from agent.paper.risk_config import PortfolioRiskConfig
from agent.paper.store import PaperStore, new_id


@dataclass(frozen=True)
class PaperSignalInput:
    """Explicit broker-facing signal payload (does not alter execution_allowed)."""

    signal_id: str
    symbol: str
    category: str
    action: str  # BUY | SELL | HOLD | BLOCKED
    risk_verdict: str  # APPROVED | VETO | etc.
    entry_price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    position_notional: Decimal | None
    signal_candle_start_ms: int | None
    created_ms: int
    interval: str = "15"


@dataclass
class BrokerResult:
    ok: bool
    reason: str
    order_id: str | None = None
    position_id: str | None = None
    fill_id: str | None = None
    detail: dict[str, Any] | None = None


class PaperBroker:
    """
    Deterministic local paper broker.

    Default application wiring must leave this OFF — call explicitly.
    Does not import Phase 6A / Bybit private order adapters.
    """

    def __init__(
        self,
        store: PaperStore,
        config: PaperBrokerConfig | None = None,
        portfolio_risk: PortfolioRiskConfig | None = None,
    ) -> None:
        self.store = store
        self.config = config or PaperBrokerConfig()
        # Optional Prompt 66 portfolio risk. None → legacy 65A guards only.
        self.portfolio_risk = portfolio_risk

    def create_session(
        self, *, now_ms: int, session_id: str | None = None
    ) -> PaperSession:
        sess = self.store.create_session(
            config=self.config, now_ms=now_ms, session_id=session_id
        )
        if self.portfolio_risk is not None:
            from agent.paper.equity import utc_day_key

            with self.store.transaction() as conn:
                self.store.upsert_risk_state(
                    conn,
                    session_id=sess.session_id,
                    halted=False,
                    halt_reason=None,
                    halt_ms=None,
                    peak_marked_equity=sess.initial_balance,
                    day_key=utc_day_key(now_ms),
                    day_start_equity=sess.initial_balance,
                    updated_ms=now_ms,
                )
                self.store.insert_equity_snapshot(
                    conn,
                    session_id=sess.session_id,
                    as_of_ms=now_ms,
                    available=sess.available_balance,
                    reserved=sess.reserved_capital,
                    realized_pnl=sess.realized_pnl,
                    unrealized_pnl=Decimal("0"),
                    marked_equity=sess.initial_balance,
                    valuation_status="flat",
                    open_position_count=0,
                    gross_exposure=Decimal("0"),
                    day_key=utc_day_key(now_ms),
                )
        return sess

    def get_session(self, session_id: str) -> PaperSession | None:
        return self.store.get_session(session_id)

    # ── signal → order ────────────────────────────────────────────────────

    def submit_signal(
        self, *, session_id: str, signal: PaperSignalInput
    ) -> BrokerResult:
        sess = self.store.get_session(session_id)
        if sess is None or sess.status is not SessionStatus.ACTIVE:
            return BrokerResult(False, "SESSION_INACTIVE")

        action = (signal.action or "").upper()
        verdict = (signal.risk_verdict or "").upper()

        if action == "HOLD":
            return BrokerResult(False, "HOLD_IGNORED")
        if action == "BLOCKED":
            return BrokerResult(False, "BLOCKED_IGNORED")
        if verdict in {"VETO", "VETOED", "BLOCKED"}:
            return BrokerResult(False, "RISK_VETO_IGNORED")
        if verdict != "APPROVED":
            return BrokerResult(False, "RISK_NOT_APPROVED")

        if action == "SELL":
            # Risk-reducing exits remain eligible even when portfolio halted.
            return self._submit_sell_to_close(session_id=session_id, signal=signal)

        if action != "BUY":
            return BrokerResult(False, "UNSUPPORTED_ACTION")

        if self.portfolio_risk is not None:
            risk_view = load_risk_state_view(self.store, session_id)
            if risk_view.halted and not exit_allowed_while_halted(action=action):
                return BrokerResult(
                    False,
                    "PORTFOLIO_HALTED",
                    detail={"halt_reason": risk_view.halt_reason},
                )

        return self._submit_buy(session_id=session_id, signal=signal, sess=sess)

    def _submit_buy(
        self,
        *,
        session_id: str,
        signal: PaperSignalInput,
        sess: PaperSession,
    ) -> BrokerResult:
        existing = self.store.get_order_by_signal(session_id, signal.signal_id, "BUY")
        if existing is not None:
            return BrokerResult(
                True,
                "DUPLICATE_SIGNAL",
                order_id=existing.order_id,
                detail={"status": existing.status.value},
            )

        if signal.entry_price is None or not _finite_positive(signal.entry_price):
            return self._reject_order(
                session_id=session_id,
                signal=signal,
                side=OrderSide.BUY,
                quantity=Decimal("0"),
                reason="INVALID_ENTRY_PRICE",
            )

        if not signal.category:
            return self._reject_order(
                session_id=session_id,
                signal=signal,
                side=OrderSide.BUY,
                quantity=Decimal("0"),
                reason="UNSUPPORTED_CATEGORY",
            )

        open_positions = self.store.get_open_positions(session_id)
        pending = [
            o
            for o in self.store.list_pending_orders(session_id)
            if o.side is OrderSide.BUY
        ]
        pending_exposure = sum(
            (notional(o.quantity, o.intended_entry_price) for o in pending),
            Decimal("0"),
        )

        # Prompt 66 portfolio risk path (optional)
        if self.portfolio_risk is not None:
            if signal.stop_loss is None or signal.take_profit is None:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=Decimal("0"),
                    reason="MISSING_SL_TP",
                )
            risk_view = load_risk_state_view(self.store, session_id)
            pr = evaluate_portfolio_entry(
                session=sess,
                open_positions=open_positions,
                pending_buy_exposure=pending_exposure,
                proposed=ProposedEntry(
                    symbol=signal.symbol,
                    category=signal.category,
                    side="BUY",
                    entry_price=d(signal.entry_price),
                    stop_loss=d(signal.stop_loss),
                    take_profit=d(signal.take_profit),
                    requested_notional=signal.position_notional,
                ),
                config=self.portfolio_risk,
                risk_state=risk_view,
                now_ms=signal.created_ms,
            )
            if pr.verdict is PortfolioRiskVerdict.HALTED:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=pr.sized_quantity or Decimal("0"),
                    reason=pr.reason_codes[0] if pr.reason_codes else "PORTFOLIO_HALTED",
                )
            if pr.verdict is PortfolioRiskVerdict.DATA_UNAVAILABLE:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=Decimal("0"),
                    reason=pr.reason_codes[0] if pr.reason_codes else "DATA_UNAVAILABLE",
                )
            if not pr.approved or pr.sized_quantity is None or pr.sized_quantity <= 0:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=pr.sized_quantity or Decimal("0"),
                    reason=pr.reason_codes[0] if pr.reason_codes else "PORTFOLIO_REJECTED",
                )
            qty = pr.sized_quantity
        else:
            # Legacy 65A path
            if signal.position_notional is None or signal.position_notional <= 0:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=Decimal("0"),
                    reason="INVALID_NOTIONAL",
                )

            qty = q(d(signal.position_notional) / d(signal.entry_price))
            if qty <= 0:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=qty,
                    reason="INVALID_QUANTITY",
                )

            if len(open_positions) >= self.config.max_open_positions:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=qty,
                    reason="MAX_OPEN_POSITIONS",
                )

            if self.config.one_position_per_symbol:
                if self.store.get_open_position_for_symbol(session_id, signal.symbol):
                    return self._reject_order(
                        session_id=session_id,
                        signal=signal,
                        side=OrderSide.BUY,
                        quantity=qty,
                        reason="SYMBOL_ALREADY_OPEN",
                    )

            if pending and self.config.one_position_per_symbol:
                if any(o.symbol == signal.symbol for o in pending):
                    return self._reject_order(
                        session_id=session_id,
                        signal=signal,
                        side=OrderSide.BUY,
                        quantity=qty,
                        reason="SYMBOL_PENDING_ORDER",
                    )

            est_notional = notional(qty, signal.entry_price)
            open_exposure = sum(
                (notional(p.quantity, p.entry_price) for p in open_positions),
                Decimal("0"),
            )
            if (
                open_exposure + pending_exposure + est_notional
                > self.config.max_total_exposure
            ):
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=qty,
                    reason="MAX_EXPOSURE",
                )

            slip_mult = Decimal("1") + (self.config.slippage_bps / Decimal("10000"))
            est_cost = q(
                est_notional * slip_mult * (Decimal("1") + self.config.fee_rate)
            )
            if sess.available_balance < est_cost:
                return self._reject_order(
                    session_id=session_id,
                    signal=signal,
                    side=OrderSide.BUY,
                    quantity=qty,
                    reason="INSUFFICIENT_FUNDS",
                )

        order = PaperOrder(
            order_id=new_id("po"),
            session_id=session_id,
            source_signal_id=signal.signal_id,
            symbol=signal.symbol,
            category=signal.category,
            side=OrderSide.BUY,
            quantity=qty,
            intended_entry_price=d(signal.entry_price),
            status=OrderStatus.PENDING,
            created_ms=signal.created_ms,
            stop_loss=d(signal.stop_loss) if signal.stop_loss is not None else None,
            take_profit=d(signal.take_profit) if signal.take_profit is not None else None,
            signal_candle_start_ms=signal.signal_candle_start_ms,
            simulated=True,
        )
        try:
            with self.store.transaction() as conn:
                self.store.insert_order(conn, order)
                self.store.append_event(
                    conn,
                    session_id=session_id,
                    event_type="ORDER_PENDING",
                    payload={
                        "order_id": order.order_id,
                        "signal_id": signal.signal_id,
                        "side": "BUY",
                        "quantity": str(qty),
                    },
                    created_ms=signal.created_ms,
                    idempotency_key=f"order_pending:{order.order_id}",
                )
        except Exception as exc:  # noqa: BLE001
            # Unique constraint race → treat as duplicate
            dup = self.store.get_order_by_signal(session_id, signal.signal_id, "BUY")
            if dup is not None:
                return BrokerResult(
                    True, "DUPLICATE_SIGNAL", order_id=dup.order_id
                )
            return BrokerResult(False, f"ORDER_INSERT_FAILED:{type(exc).__name__}")

        return BrokerResult(True, "ORDER_PENDING", order_id=order.order_id)

    def _submit_sell_to_close(
        self, *, session_id: str, signal: PaperSignalInput
    ) -> BrokerResult:
        """SELL closes an eligible open long; never opens a short in MVP."""
        if self.config.allow_short:
            return BrokerResult(False, "SHORTS_NOT_IMPLEMENTED")

        existing = self.store.get_order_by_signal(session_id, signal.signal_id, "SELL")
        if existing is not None:
            return BrokerResult(
                True,
                "DUPLICATE_SIGNAL",
                order_id=existing.order_id,
                detail={"status": existing.status.value},
            )

        pos = self.store.get_open_position_for_symbol(session_id, signal.symbol)
        if pos is None:
            return self._reject_order(
                session_id=session_id,
                signal=signal,
                side=OrderSide.SELL,
                quantity=Decimal("0"),
                reason="NO_OPEN_LONG",
            )

        order = PaperOrder(
            order_id=new_id("po"),
            session_id=session_id,
            source_signal_id=signal.signal_id,
            symbol=signal.symbol,
            category=signal.category or pos.category,
            side=OrderSide.SELL,
            quantity=pos.quantity,
            intended_entry_price=d(signal.entry_price or pos.entry_price),
            status=OrderStatus.PENDING,
            created_ms=signal.created_ms,
            stop_loss=None,
            take_profit=None,
            signal_candle_start_ms=signal.signal_candle_start_ms,
            simulated=True,
        )
        try:
            with self.store.transaction() as conn:
                self.store.insert_order(conn, order)
                self.store.append_event(
                    conn,
                    session_id=session_id,
                    event_type="EXIT_ORDER_PENDING",
                    payload={
                        "order_id": order.order_id,
                        "signal_id": signal.signal_id,
                        "position_id": pos.position_id,
                    },
                    created_ms=signal.created_ms,
                    idempotency_key=f"order_pending:{order.order_id}",
                )
        except Exception:  # noqa: BLE001
            dup = self.store.get_order_by_signal(session_id, signal.signal_id, "SELL")
            if dup is not None:
                return BrokerResult(
                    True, "DUPLICATE_SIGNAL", order_id=dup.order_id
                )
            return BrokerResult(False, "ORDER_INSERT_FAILED")

        return BrokerResult(
            True,
            "EXIT_ORDER_PENDING",
            order_id=order.order_id,
            position_id=pos.position_id,
        )

    def _reject_order(
        self,
        *,
        session_id: str,
        signal: PaperSignalInput,
        side: OrderSide,
        quantity: Decimal,
        reason: str,
    ) -> BrokerResult:
        order = PaperOrder(
            order_id=new_id("po"),
            session_id=session_id,
            source_signal_id=signal.signal_id,
            symbol=signal.symbol,
            category=signal.category or "spot",
            side=side,
            quantity=quantity,
            intended_entry_price=d(signal.entry_price or 0),
            status=OrderStatus.REJECTED,
            created_ms=signal.created_ms,
            rejection_reason=reason,
            stop_loss=d(signal.stop_loss) if signal.stop_loss is not None else None,
            take_profit=d(signal.take_profit) if signal.take_profit is not None else None,
            signal_candle_start_ms=signal.signal_candle_start_ms,
            simulated=True,
        )
        try:
            with self.store.transaction() as conn:
                self.store.insert_order(conn, order)
                self.store.append_event(
                    conn,
                    session_id=session_id,
                    event_type="ORDER_REJECTED",
                    payload={"order_id": order.order_id, "reason": reason},
                    created_ms=signal.created_ms,
                    idempotency_key=f"order_rejected:{session_id}:{signal.signal_id}:{side.value}:{reason}",
                )
        except Exception:  # noqa: BLE001
            dup = self.store.get_order_by_signal(
                session_id, signal.signal_id, side.value
            )
            if dup is not None:
                return BrokerResult(
                    False if dup.status is OrderStatus.REJECTED else True,
                    dup.rejection_reason or "DUPLICATE_SIGNAL",
                    order_id=dup.order_id,
                )
            return BrokerResult(False, reason)
        return BrokerResult(False, reason, order_id=order.order_id)

    # ── candle processing ─────────────────────────────────────────────────

    def process_candle(
        self,
        *,
        session_id: str,
        candle: PaperCandle,
        interval: str = "15",
    ) -> list[BrokerResult]:
        """
        Advance simulation with one confirmed candle.

        - Rejects out-of-order / duplicate candles via cursor.
        - Fills pending entry at next eligible open (no look-ahead / invented price).
        - Marks open positions; evaluates SL/TP.
        """
        results: list[BrokerResult] = []
        if not candle.valid():
            return [BrokerResult(False, "INVALID_OHLC")]

        symbol = candle.symbol
        if not symbol:
            return [BrokerResult(False, "MISSING_SYMBOL")]

        cursor = self.store.get_candle_cursor(session_id, symbol, interval)
        if cursor is not None and candle.start_ms < cursor:
            return [BrokerResult(False, "OUT_OF_ORDER_CANDLE")]
        if cursor is not None and candle.start_ms == cursor:
            return [BrokerResult(True, "DUPLICATE_CANDLE")]

        event_key = f"candle:{symbol}:{interval}:{candle.start_ms}"
        if self.store.has_processed_event(session_id, event_key):
            return [BrokerResult(True, "DUPLICATE_CANDLE")]

        # Fill pending BUY orders whose signal candle precedes this bar.
        for order in self.store.list_pending_orders(session_id):
            if order.symbol != symbol:
                continue
            if order.side is OrderSide.BUY:
                if (
                    order.signal_candle_start_ms is not None
                    and candle.start_ms <= order.signal_candle_start_ms
                ):
                    # No look-ahead: need a later confirmed candle.
                    results.append(
                        BrokerResult(
                            True,
                            "AWAITING_NEXT_CANDLE",
                            order_id=order.order_id,
                        )
                    )
                    continue
                r = self._fill_entry(session_id=session_id, order=order, candle=candle)
                results.append(r)
            elif order.side is OrderSide.SELL:
                if (
                    order.signal_candle_start_ms is not None
                    and candle.start_ms <= order.signal_candle_start_ms
                ):
                    results.append(
                        BrokerResult(
                            True,
                            "AWAITING_NEXT_CANDLE",
                            order_id=order.order_id,
                        )
                    )
                    continue
                r = self._fill_signal_exit(
                    session_id=session_id, order=order, candle=candle
                )
                results.append(r)

        # Mark-to-market + SL/TP for open longs
        for pos in self.store.get_open_positions(session_id):
            if pos.symbol != symbol:
                continue
            self._mark_to_market(session_id=session_id, pos=pos, candle=candle)
            exit_r = self._maybe_sl_tp(session_id=session_id, pos=pos, candle=candle)
            if exit_r is not None:
                results.append(exit_r)

        # Advance cursor atomically with processed marker (+ optional equity/halt)
        with self.store.transaction() as conn:
            inserted = self.store.mark_processed_event(
                conn,
                session_id=session_id,
                event_key=event_key,
                created_ms=candle.start_ms,
            )
            if inserted:
                self.store.set_candle_cursor(
                    conn,
                    session_id=session_id,
                    symbol=symbol,
                    interval=interval,
                    candle_start_ms=candle.start_ms,
                )
            if self.portfolio_risk is not None:
                sess_now = self.store.get_session(session_id)
                if sess_now is not None:
                    prior = load_risk_state_view(self.store, session_id)
                    apply_equity_and_limits(
                        self.store,
                        conn,
                        session=sess_now,
                        open_positions=self.store.get_open_positions(session_id),
                        prior_state=prior,
                        config=self.portfolio_risk,
                        as_of_ms=candle.start_ms,
                    )

        if not results:
            results.append(BrokerResult(True, "CANDLE_PROCESSED"))
        return results

    def _fill_entry(
        self,
        *,
        session_id: str,
        order: PaperOrder,
        candle: PaperCandle,
    ) -> BrokerResult:
        fill_event = f"fill_entry:{order.order_id}:{candle.start_ms}"
        if self.store.has_processed_event(session_id, fill_event):
            return BrokerResult(True, "DUPLICATE_FILL", order_id=order.order_id)

        sim = simulate_entry_fill(
            candle=candle,
            side="BUY",
            quantity=order.quantity,
            config=self.config,
        )
        if sim is None:
            return BrokerResult(False, "INVALID_FILL_CANDLE", order_id=order.order_id)

        reserve = capital_to_reserve(
            quantity=order.quantity, fill_price=sim.price, fee=sim.fee
        )

        try:
            with self.store.transaction() as conn:
                if not self.store.mark_processed_event(
                    conn,
                    session_id=session_id,
                    event_key=fill_event,
                    created_ms=candle.start_ms,
                ):
                    return BrokerResult(True, "DUPLICATE_FILL", order_id=order.order_id)

                sess_row = self.store.get_session_for_update(conn, session_id)
                if sess_row is None:
                    raise RuntimeError("session missing")
                available = d(sess_row.available_balance)
                reserved = d(sess_row.reserved_capital)
                fees_paid = d(sess_row.fees_paid)
                realized = d(sess_row.realized_pnl)

                if available < reserve:
                    self.store.update_order_rejected(
                        conn, order_id=order.order_id, reason="INSUFFICIENT_FUNDS"
                    )
                    self.store.append_event(
                        conn,
                        session_id=session_id,
                        event_type="ORDER_REJECTED",
                        payload={
                            "order_id": order.order_id,
                            "reason": "INSUFFICIENT_FUNDS",
                        },
                        created_ms=candle.start_ms,
                        idempotency_key=f"reject_fill:{order.order_id}",
                    )
                    return BrokerResult(
                        False, "INSUFFICIENT_FUNDS", order_id=order.order_id
                    )

                # Atomic portfolio halt / exposure recheck (Prompt 66)
                if self.portfolio_risk is not None:
                    if self.store.risk_halted_in_txn(conn, session_id):
                        self.store.update_order_rejected(
                            conn, order_id=order.order_id, reason="PORTFOLIO_HALTED"
                        )
                        return BrokerResult(
                            False, "PORTFOLIO_HALTED", order_id=order.order_id
                        )

                # Re-check max positions inside txn
                max_pos = (
                    self.portfolio_risk.max_open_positions
                    if self.portfolio_risk is not None
                    else self.config.max_open_positions
                )
                open_count = self.store.count_open_positions(conn, session_id)
                if int(open_count) >= max_pos:
                    self.store.update_order_rejected(
                        conn, order_id=order.order_id, reason="MAX_OPEN_POSITIONS"
                    )
                    return BrokerResult(
                        False, "MAX_OPEN_POSITIONS", order_id=order.order_id
                    )

                self.store.update_order_filled(
                    conn,
                    order_id=order.order_id,
                    fill_price=sim.price,
                    fee=sim.fee,
                    slippage=sim.slippage,
                    filled_ms=candle.start_ms,
                )
                fill = PaperFill(
                    fill_id=new_id("pf"),
                    order_id=order.order_id,
                    session_id=session_id,
                    symbol=order.symbol,
                    side=OrderSide.BUY,
                    quantity=order.quantity,
                    price=sim.price,
                    fee=sim.fee,
                    slippage=sim.slippage,
                    filled_ms=candle.start_ms,
                    candle_start_ms=candle.start_ms,
                    role="entry",
                )
                self.store.insert_fill(conn, fill)
                pos = PaperPosition(
                    position_id=new_id("pp"),
                    session_id=session_id,
                    symbol=order.symbol,
                    category=order.category,
                    status=PositionStatus.OPEN,
                    quantity=order.quantity,
                    entry_price=sim.price,
                    entry_fee=sim.fee,
                    entry_order_id=order.order_id,
                    entry_signal_id=order.source_signal_id,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    opened_ms=candle.start_ms,
                    mark_price=candle.close,
                    unrealized_pnl=long_unrealized_pnl(
                        quantity=order.quantity,
                        entry_price=sim.price,
                        mark_price=candle.close,
                    ),
                )
                self.store.insert_position(conn, pos)
                new_available = q(available - reserve)
                new_reserved = q(reserved + reserve)
                new_fees = q(fees_paid + sim.fee)
                self.store.update_session_balances(
                    conn,
                    session_id=session_id,
                    available=new_available,
                    reserved=new_reserved,
                    realized_pnl=realized,
                    fees_paid=new_fees,
                    updated_ms=candle.start_ms,
                )
                self.store.append_event(
                    conn,
                    session_id=session_id,
                    event_type="POSITION_OPENED",
                    payload={
                        "position_id": pos.position_id,
                        "order_id": order.order_id,
                        "fill_price": str(sim.price),
                        "quantity": str(order.quantity),
                        "fee": str(sim.fee),
                    },
                    created_ms=candle.start_ms,
                    idempotency_key=f"pos_open:{pos.position_id}",
                )
        except Exception as exc:  # noqa: BLE001
            return BrokerResult(
                False,
                f"FILL_FAILED:{type(exc).__name__}",
                order_id=order.order_id,
            )

        return BrokerResult(
            True,
            "FILLED_ENTRY",
            order_id=order.order_id,
            position_id=pos.position_id,
            fill_id=fill.fill_id,
            detail={"fill_price": str(sim.price), "fee": str(sim.fee)},
        )

    def _fill_signal_exit(
        self,
        *,
        session_id: str,
        order: PaperOrder,
        candle: PaperCandle,
    ) -> BrokerResult:
        pos = self.store.get_open_position_for_symbol(session_id, order.symbol)
        if pos is None:
            with self.store.transaction() as conn:
                self.store.update_order_rejected(
                    conn, order_id=order.order_id, reason="NO_OPEN_LONG"
                )
            return BrokerResult(False, "NO_OPEN_LONG", order_id=order.order_id)

        exit_event = f"exit:{pos.position_id}:{order.order_id}"
        if self.store.has_processed_event(session_id, exit_event):
            return BrokerResult(
                True, "DUPLICATE_EXIT", order_id=order.order_id, position_id=pos.position_id
            )

        from agent.paper.fills import simulate_exit_fill

        sim = simulate_exit_fill(
            candle=candle,
            side="SELL",
            quantity=pos.quantity,
            reference_price=candle.open,
            config=self.config,
            use_reference_as_base=True,
        )
        if sim is None:
            return BrokerResult(False, "INVALID_FILL_CANDLE", order_id=order.order_id)

        return self._close_position(
            session_id=session_id,
            pos=pos,
            exit_order=order,
            exit_price=sim.price,
            exit_fee=sim.fee,
            exit_slippage=sim.slippage,
            exit_reason=ExitReason.SIGNAL_SELL.value,
            candle_start_ms=candle.start_ms,
            exit_event_key=exit_event,
        )

    def _mark_to_market(
        self,
        *,
        session_id: str,
        pos: PaperPosition,
        candle: PaperCandle,
    ) -> None:
        upnl = long_unrealized_pnl(
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            mark_price=candle.close,
        )
        with self.store.transaction() as conn:
            self.store.mark_position(
                conn,
                position_id=pos.position_id,
                mark_price=candle.close,
                unrealized_pnl=upnl,
            )

    def _maybe_sl_tp(
        self,
        *,
        session_id: str,
        pos: PaperPosition,
        candle: PaperCandle,
    ) -> BrokerResult | None:
        # Refresh pos in case concurrent close
        fresh = self.store.get_position(pos.position_id)
        if fresh is None or fresh.status is not PositionStatus.OPEN:
            return None

        exit_event = f"exit_sltp:{pos.position_id}:{candle.start_ms}"
        if self.store.has_processed_event(session_id, exit_event):
            return BrokerResult(
                True, "DUPLICATE_EXIT", position_id=pos.position_id
            )

        trigger = evaluate_long_exit(
            candle=candle,
            quantity=fresh.quantity,
            stop_loss=fresh.stop_loss,
            take_profit=fresh.take_profit,
            config=self.config,
        )
        if trigger is None:
            return None

        # Synthetic exit order for journal
        exit_order = PaperOrder(
            order_id=new_id("po"),
            session_id=session_id,
            source_signal_id=f"sltp:{fresh.entry_signal_id}",
            symbol=fresh.symbol,
            category=fresh.category,
            side=OrderSide.SELL,
            quantity=fresh.quantity,
            intended_entry_price=trigger.reference_price,
            status=OrderStatus.PENDING,
            created_ms=candle.start_ms,
            simulated=True,
        )

        return self._close_position(
            session_id=session_id,
            pos=fresh,
            exit_order=exit_order,
            exit_price=trigger.fill.price,
            exit_fee=trigger.fill.fee,
            exit_slippage=trigger.fill.slippage,
            exit_reason=trigger.reason.value,
            candle_start_ms=candle.start_ms,
            exit_event_key=exit_event,
            insert_exit_order=True,
        )

    def _close_position(
        self,
        *,
        session_id: str,
        pos: PaperPosition,
        exit_order: PaperOrder,
        exit_price: Decimal,
        exit_fee: Decimal,
        exit_slippage: Decimal,
        exit_reason: str,
        candle_start_ms: int,
        exit_event_key: str,
        insert_exit_order: bool = False,
    ) -> BrokerResult:
        try:
            with self.store.transaction() as conn:
                if not self.store.mark_processed_event(
                    conn,
                    session_id=session_id,
                    event_key=exit_event_key,
                    created_ms=candle_start_ms,
                ):
                    return BrokerResult(
                        True,
                        "DUPLICATE_EXIT",
                        order_id=exit_order.order_id,
                        position_id=pos.position_id,
                    )

                # Also block any other exit key for this position
                pos_exit_key = f"pos_closed:{pos.position_id}"
                if not self.store.mark_processed_event(
                    conn,
                    session_id=session_id,
                    event_key=pos_exit_key,
                    created_ms=candle_start_ms,
                ):
                    return BrokerResult(
                        True,
                        "DUPLICATE_EXIT",
                        position_id=pos.position_id,
                    )

                sess_row = self.store.get_session_for_update(conn, session_id)
                if sess_row is None:
                    raise RuntimeError("session missing")
                available = d(sess_row.available_balance)
                reserved = d(sess_row.reserved_capital)
                fees_paid = d(sess_row.fees_paid)
                realized = d(sess_row.realized_pnl)

                entry_reserve = capital_to_reserve(
                    quantity=pos.quantity,
                    fill_price=pos.entry_price,
                    fee=pos.entry_fee,
                )
                exit_proceeds = q(notional(pos.quantity, exit_price) - exit_fee)
                net = long_net_pnl(
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    entry_fee=pos.entry_fee,
                    exit_fee=exit_fee,
                )

                if insert_exit_order:
                    self.store.insert_order(conn, exit_order)
                    conn.flush()

                self.store.update_order_filled(
                    conn,
                    order_id=exit_order.order_id,
                    fill_price=exit_price,
                    fee=exit_fee,
                    slippage=exit_slippage,
                    filled_ms=candle_start_ms,
                )
                fill = PaperFill(
                    fill_id=new_id("pf"),
                    order_id=exit_order.order_id,
                    session_id=session_id,
                    symbol=pos.symbol,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    price=exit_price,
                    fee=exit_fee,
                    slippage=exit_slippage,
                    filled_ms=candle_start_ms,
                    candle_start_ms=candle_start_ms,
                    role="exit",
                )
                self.store.insert_fill(conn, fill)
                self.store.close_position(
                    conn,
                    position_id=pos.position_id,
                    exit_price=exit_price,
                    exit_fee=exit_fee,
                    exit_order_id=exit_order.order_id,
                    exit_reason=exit_reason,
                    realized_pnl=net,
                    closed_ms=candle_start_ms,
                )

                new_reserved = q(reserved - entry_reserve)
                if new_reserved < 0:
                    new_reserved = Decimal("0")
                # Return reserved capital, then apply net PnL to available.
                # Invariant: available' = available + entry_reserve + net
                # (entry_reserve already included entry fee; net subtracts both fees)
                new_available = q(available + entry_reserve + net)
                new_fees = q(fees_paid + exit_fee)
                new_realized = q(realized + net)
                self.store.update_session_balances(
                    conn,
                    session_id=session_id,
                    available=new_available,
                    reserved=new_reserved,
                    realized_pnl=new_realized,
                    fees_paid=new_fees,
                    updated_ms=candle_start_ms,
                )
                self.store.append_event(
                    conn,
                    session_id=session_id,
                    event_type="POSITION_CLOSED",
                    payload={
                        "position_id": pos.position_id,
                        "exit_reason": exit_reason,
                        "exit_price": str(exit_price),
                        "net_pnl": str(net),
                        "exit_proceeds": str(exit_proceeds),
                    },
                    created_ms=candle_start_ms,
                    idempotency_key=f"pos_close:{pos.position_id}",
                )
        except Exception as exc:  # noqa: BLE001
            return BrokerResult(
                False,
                f"CLOSE_FAILED:{type(exc).__name__}",
                order_id=exit_order.order_id,
                position_id=pos.position_id,
            )

        return BrokerResult(
            True,
            f"CLOSED_{exit_reason}",
            order_id=exit_order.order_id,
            position_id=pos.position_id,
            fill_id=fill.fill_id,
            detail={
                "exit_price": str(exit_price),
                "net_pnl": str(net),
                "exit_fee": str(exit_fee),
            },
        )


def _finite_positive(value: Decimal) -> bool:
    try:
        v = float(value)
        return math.isfinite(v) and v > 0
    except Exception:  # noqa: BLE001
        return False
