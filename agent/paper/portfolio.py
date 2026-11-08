"""Portfolio risk state updates from reconciled equity (durable halt / peak / day)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent.paper.config import d
from agent.paper.equity import (
    EquitySnapshot,
    daily_loss_fraction,
    drawdown_fraction,
    reconcile_equity,
    utc_day_key,
)
from agent.paper.models import PaperPosition, PaperSession
from agent.paper.risk import PortfolioRiskStateView
from agent.paper.risk_config import PortfolioRiskConfig
from agent.paper.store import PaperStore


def load_risk_state_view(store: PaperStore, session_id: str) -> PortfolioRiskStateView:
    row = store.get_risk_state(session_id)
    if row is None:
        return PortfolioRiskStateView()
    return PortfolioRiskStateView(
        halted=bool(row["halted"]),
        halt_reason=row["halt_reason"],
        peak_marked_equity=d(row["peak_marked_equity"])
        if row["peak_marked_equity"] is not None
        else None,
        day_key=row["day_key"],
        day_start_equity=d(row["day_start_equity"])
        if row["day_start_equity"] is not None
        else None,
    )


def risk_state_from_row(row: dict | None) -> PortfolioRiskStateView:
    if row is None:
        return PortfolioRiskStateView()
    return PortfolioRiskStateView(
        halted=bool(row["halted"]),
        halt_reason=row["halt_reason"],
        peak_marked_equity=d(row["peak_marked_equity"])
        if row.get("peak_marked_equity") is not None
        else None,
        day_key=row.get("day_key"),
        day_start_equity=d(row["day_start_equity"])
        if row.get("day_start_equity") is not None
        else None,
    )


def apply_equity_and_limits(
    store: PaperStore,
    conn: Any,
    *,
    session: PaperSession,
    open_positions: list[PaperPosition],
    prior_state: PortfolioRiskStateView,
    config: PortfolioRiskConfig,
    as_of_ms: int,
) -> EquitySnapshot:
    """
    Persist equity snapshot and update peak/day/halt.

    Halt is durable: process restart does NOT clear halted.
    New UTC day rolls day_start_equity but does NOT clear halt.
    """
    equity = reconcile_equity(
        session=session, open_positions=open_positions, now_ms=as_of_ms
    )
    day_key = utc_day_key(as_of_ms)

    peak = prior_state.peak_marked_equity
    day_start = prior_state.day_start_equity
    state_day = prior_state.day_key
    halted = prior_state.halted
    halt_reason = prior_state.halt_reason
    halt_ms: int | None = None

    if equity.marked_equity is not None:
        if peak is None or equity.marked_equity > peak:
            peak = equity.marked_equity
        if state_day != day_key or day_start is None:
            day_start = equity.marked_equity
            state_day = day_key
        else:
            dloss = daily_loss_fraction(
                day_start=day_start, current=equity.marked_equity
            )
            if dloss is not None and dloss >= config.max_daily_loss_fraction:
                halted = True
                halt_reason = "DAILY_LOSS_LIMIT"
                halt_ms = as_of_ms
        if peak is not None:
            dd = drawdown_fraction(peak=peak, current=equity.marked_equity)
            if dd is not None and dd >= config.max_drawdown_fraction:
                halted = True
                halt_reason = halt_reason or "MAX_DRAWDOWN_LIMIT"
                halt_ms = as_of_ms

    store.insert_equity_snapshot(
        conn,
        session_id=session.session_id,
        as_of_ms=as_of_ms,
        available=equity.available_balance,
        reserved=equity.reserved_capital,
        realized_pnl=equity.realized_pnl,
        unrealized_pnl=equity.unrealized_pnl,
        marked_equity=equity.marked_equity,
        valuation_status=equity.valuation_status.value,
        open_position_count=equity.open_position_count,
        gross_exposure=equity.gross_exposure_entry,
        day_key=day_key,
    )

    if halted and halt_ms is None:
        # Keep prior halt timestamp if already halted.
        prior_halt_ms = store.risk_halt_ms_in_txn(conn, session.session_id)
        if prior_halt_ms is not None:
            halt_ms = prior_halt_ms
        else:
            halt_ms = as_of_ms

    store.upsert_risk_state(
        conn,
        session_id=session.session_id,
        halted=halted,
        halt_reason=halt_reason if halted else None,
        halt_ms=halt_ms if halted else None,
        peak_marked_equity=peak,
        day_key=state_day,
        day_start_equity=day_start,
        updated_ms=as_of_ms,
    )
    return equity
