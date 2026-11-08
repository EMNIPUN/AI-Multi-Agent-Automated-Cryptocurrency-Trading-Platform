"""Read-only analytics service over PaperReadStore."""

from __future__ import annotations

from agent.paper.analytics.aggregator import (
    aggregate_session_analytics,
    build_closed_trades,
)
from agent.paper.analytics.equity_curve import (
    marked_equity_series,
    realized_balance_series,
)
from agent.paper.analytics.models import ClosedTradeMetrics, SessionAnalytics
from agent.paper.models import PositionStatus
from agent.paper.read_store import PaperDbUnavailable, PaperReadStore


class AnalyticsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def compute_session_analytics(
    store: PaperReadStore,
    session_id: str,
    *,
    symbol: str | None = None,
    exit_from_ms: int | None = None,
    exit_to_ms: int | None = None,
) -> SessionAnalytics:
    if not store.exists():
        raise AnalyticsError("paper_db_missing", "Paper database file not found")
    try:
        sess = store.get_session(session_id)
    except PaperDbUnavailable as exc:
        raise AnalyticsError("paper_db_error", "Paper database unreadable") from exc
    if sess is None:
        raise AnalyticsError("session_not_found", f"Session {session_id} not found")

    closed = store.list_closed_positions(
        session_id,
        symbol=symbol,
        exit_from_ms=exit_from_ms,
        exit_to_ms=exit_to_ms,
        limit=1000,
    )
    opens = store.list_positions(
        session_id, status=PositionStatus.OPEN.value, limit=200
    )
    snapshots = store.list_equity_snapshots(session_id, limit=5000)
    return aggregate_session_analytics(
        session=sess,
        closed_positions=closed,
        open_position_count=len(opens),
        equity_snapshots=snapshots,
    )


def list_trade_metrics(
    store: PaperReadStore,
    session_id: str,
    *,
    symbol: str | None = None,
    exit_from_ms: int | None = None,
    exit_to_ms: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ClosedTradeMetrics], list[str]]:
    if not store.exists():
        raise AnalyticsError("paper_db_missing", "Paper database file not found")
    sess = store.get_session(session_id)
    if sess is None:
        raise AnalyticsError("session_not_found", f"Session {session_id} not found")
    closed = store.list_closed_positions(
        session_id,
        symbol=symbol,
        exit_from_ms=exit_from_ms,
        exit_to_ms=exit_to_ms,
        limit=1000,
    )
    trades, warnings = build_closed_trades(closed)
    return trades[offset : offset + limit], warnings


def list_equity_points(
    store: PaperReadStore,
    session_id: str,
    *,
    series: str = "marked",
    from_ms: int | None = None,
    to_ms: int | None = None,
) -> tuple[list, list[str]]:
    if not store.exists():
        raise AnalyticsError("paper_db_missing", "Paper database file not found")
    if store.get_session(session_id) is None:
        raise AnalyticsError("session_not_found", f"Session {session_id} not found")
    snaps = store.list_equity_snapshots(
        session_id, from_ms=from_ms, to_ms=to_ms, limit=5000
    )
    if series == "realized_balance":
        return realized_balance_series(snaps)
    return marked_equity_series(snaps)
