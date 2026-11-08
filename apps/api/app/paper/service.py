"""Read-only paper API service — persists authority is PaperReadStore / SQLite."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from agent.paper.integration import PAPER_BROKER_AUTO_ATTACH
from agent.paper.models import PaperOrder, PaperPosition, PaperSession, PositionStatus
from agent.paper.read_store import PaperDbUnavailable, PaperReadStore
from apps.api.app.paper.schemas import (
    PaperAccountResponse,
    PaperEventItem,
    PaperEventListResponse,
    PaperFillItem,
    PaperFillListResponse,
    PaperOrderItem,
    PaperOrderListResponse,
    PaperPositionItem,
    PaperPositionListResponse,
    PaperSessionListResponse,
    PaperSessionSummary,
    PaperSignalLinkResponse,
    PaperStatusResponse,
)

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,32}$")
_SIGNAL_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")


def dec_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def validate_session_id(session_id: str) -> str:
    text = (session_id or "").strip()
    if not _SESSION_ID_RE.match(text):
        raise ValueError("invalid_session_id")
    return text


def validate_symbol(symbol: str | None) -> str | None:
    if symbol is None or symbol == "":
        return None
    text = symbol.strip().upper()
    if not _SYMBOL_RE.match(text):
        raise ValueError("invalid_symbol")
    return text


def validate_signal_id(signal_id: str) -> str:
    text = (signal_id or "").strip()
    if not _SIGNAL_ID_RE.match(text):
        raise ValueError("invalid_signal_id")
    return text


def resolve_paper_db_path(configured: str | None) -> Path:
    raw = (configured or "").strip()
    if raw:
        return Path(raw)
    # Default relative to repo root when running from project.
    return Path("data") / "cryptonova_paper.sqlite3"


def build_status(
    *,
    enabled: bool,
    db_path: Path,
) -> PaperStatusResponse:
    if not enabled:
        return PaperStatusResponse(
            paper_read_api_enabled=False,
            broker_auto_attach=PAPER_BROKER_AUTO_ATTACH,
            db_configured=bool(str(db_path)),
            db_present=False,
            schema_version=None,
            session_count=None,
            note="Paper read API disabled — no database opened.",
        )
    present = db_path.is_file()
    schema = None
    count = None
    note = "Paper read API enabled — local SQLite read-only."
    if present:
        try:
            store = PaperReadStore(db_path)
            schema = store.schema_version()
            count = store.count_sessions()
        except PaperDbUnavailable:
            note = "Paper DB present but unreadable or invalid schema."
            present = True
    else:
        note = "Paper read API enabled — database file not found (empty)."
    return PaperStatusResponse(
        paper_read_api_enabled=True,
        broker_auto_attach=PAPER_BROKER_AUTO_ATTACH,
        db_configured=True,
        db_present=present,
        schema_version=schema,
        session_count=count,
        note=note,
    )


def session_summary(sess: PaperSession, open_count: int | None = None) -> PaperSessionSummary:
    return PaperSessionSummary(
        session_id=sess.session_id,
        status=sess.status.value,
        currency=sess.currency,
        initial_balance=dec_str(sess.initial_balance) or "0",
        available_balance=dec_str(sess.available_balance) or "0",
        reserved_capital=dec_str(sess.reserved_capital) or "0",
        realized_pnl=dec_str(sess.realized_pnl) or "0",
        fees_paid=dec_str(sess.fees_paid) or "0",
        created_ms=sess.created_ms,
        updated_ms=sess.updated_ms,
        open_position_count=open_count,
    )


def account_response(store: PaperReadStore, sess: PaperSession) -> PaperAccountResponse:
    open_count = store.count_open_positions(sess.session_id)
    upnl, all_marks = store.sum_open_unrealized(sess.session_id)
    if open_count == 0:
        upnl_status: str = "none"
        upnl_out: str | None = "0"
        equity_status = "ok"
        equity = sess.available_balance + sess.reserved_capital
        # Flat: equity ≈ available + reserved (cash identity); no mark needed.
        equity_out = dec_str(equity)
    elif not all_marks:
        upnl_status = "stale_or_partial"
        upnl_out = dec_str(upnl) if upnl is not None else None
        equity_status = "stale_or_partial"
        equity_out = None
    else:
        upnl_status = "ok"
        upnl_out = dec_str(upnl)
        equity_status = "ok"
        # Marked equity = available + reserved + unrealized (reserved holds cost basis).
        equity_out = dec_str(sess.available_balance + sess.reserved_capital + (upnl or Decimal("0")))

    return PaperAccountResponse(
        session_id=sess.session_id,
        status=sess.status.value,
        currency=sess.currency,
        initial_balance=dec_str(sess.initial_balance) or "0",
        available_balance=dec_str(sess.available_balance) or "0",
        reserved_capital=dec_str(sess.reserved_capital) or "0",
        realized_pnl=dec_str(sess.realized_pnl) or "0",
        fees_paid=dec_str(sess.fees_paid) or "0",
        open_position_count=open_count,
        unrealized_pnl=upnl_out,
        unrealized_pnl_status=upnl_status,  # type: ignore[arg-type]
        marked_equity=equity_out,
        marked_equity_status=equity_status,  # type: ignore[arg-type]
        created_ms=sess.created_ms,
        updated_ms=sess.updated_ms,
    )


def position_item(pos: PaperPosition) -> PaperPositionItem:
    has_mark = pos.mark_price is not None and pos.status is PositionStatus.OPEN
    return PaperPositionItem(
        position_id=pos.position_id,
        session_id=pos.session_id,
        symbol=pos.symbol,
        category=pos.category,
        status=pos.status.value,
        quantity=dec_str(pos.quantity) or "0",
        entry_price=dec_str(pos.entry_price) or "0",
        entry_fee=dec_str(pos.entry_fee) or "0",
        stop_loss=dec_str(pos.stop_loss),
        take_profit=dec_str(pos.take_profit),
        opened_ms=pos.opened_ms,
        closed_ms=pos.closed_ms,
        exit_price=dec_str(pos.exit_price),
        exit_fee=dec_str(pos.exit_fee) or "0",
        exit_reason=pos.exit_reason,
        realized_pnl=dec_str(pos.realized_pnl) or "0",
        mark_price=dec_str(pos.mark_price) if has_mark else (
            dec_str(pos.mark_price) if pos.mark_price is not None else None
        ),
        unrealized_pnl=dec_str(pos.unrealized_pnl) if has_mark else None,
        unrealized_pnl_status="ok" if has_mark else "unavailable",
        entry_signal_id=pos.entry_signal_id,
        entry_order_id=pos.entry_order_id,
        exit_order_id=pos.exit_order_id,
    )


def order_item(order: PaperOrder) -> PaperOrderItem:
    return PaperOrderItem(
        order_id=order.order_id,
        session_id=order.session_id,
        source_signal_id=order.source_signal_id,
        symbol=order.symbol,
        category=order.category,
        side=order.side.value,
        quantity=dec_str(order.quantity) or "0",
        intended_entry_price=dec_str(order.intended_entry_price) or "0",
        status=order.status.value,
        created_ms=order.created_ms,
        filled_ms=order.filled_ms,
        fill_price=dec_str(order.fill_price),
        fee=dec_str(order.fee) or "0",
        slippage=dec_str(order.slippage) or "0",
        rejection_reason=order.rejection_reason,
        stop_loss=dec_str(order.stop_loss),
        take_profit=dec_str(order.take_profit),
    )


def list_sessions_response(
    store: PaperReadStore, *, limit: int, offset: int
) -> PaperSessionListResponse:
    total = store.count_sessions()
    sessions = store.list_sessions(limit=limit, offset=offset)
    items = [
        session_summary(s, store.count_open_positions(s.session_id)) for s in sessions
    ]
    return PaperSessionListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


def list_positions_response(
    store: PaperReadStore,
    session_id: str,
    *,
    status: str | None,
    symbol: str | None,
    limit: int,
    offset: int,
) -> PaperPositionListResponse:
    items = [
        position_item(p)
        for p in store.list_positions(
            session_id, status=status, symbol=symbol, limit=limit, offset=offset
        )
    ]
    return PaperPositionListResponse(items=items, limit=limit, offset=offset)


def list_orders_response(
    store: PaperReadStore,
    session_id: str,
    *,
    status: str | None,
    symbol: str | None,
    source_signal_id: str | None,
    limit: int,
    offset: int,
) -> PaperOrderListResponse:
    items = [
        order_item(o)
        for o in store.list_orders(
            session_id,
            status=status,
            symbol=symbol,
            source_signal_id=source_signal_id,
            limit=limit,
            offset=offset,
        )
    ]
    return PaperOrderListResponse(items=items, limit=limit, offset=offset)


def list_fills_response(
    store: PaperReadStore,
    session_id: str,
    *,
    symbol: str | None,
    limit: int,
    offset: int,
) -> PaperFillListResponse:
    items = [
        PaperFillItem(
            fill_id=f.fill_id,
            order_id=f.order_id,
            session_id=f.session_id,
            symbol=f.symbol,
            side=f.side.value,
            quantity=dec_str(f.quantity) or "0",
            price=dec_str(f.price) or "0",
            fee=dec_str(f.fee) or "0",
            slippage=dec_str(f.slippage) or "0",
            filled_ms=f.filled_ms,
            candle_start_ms=f.candle_start_ms,
            role=f.role,
        )
        for f in store.list_fills(
            session_id, symbol=symbol, limit=limit, offset=offset
        )
    ]
    return PaperFillListResponse(items=items, limit=limit, offset=offset)


def list_events_response(
    store: PaperReadStore,
    session_id: str,
    *,
    limit: int,
    offset: int,
) -> PaperEventListResponse:
    items = [
        PaperEventItem(
            event_id=e["event_id"],
            session_id=e["session_id"],
            event_type=e["event_type"],
            payload_json=e["payload_json"],
            created_ms=int(e["created_ms"]),
            idempotency_key=e["idempotency_key"],
        )
        for e in store.list_events(session_id, limit=limit, offset=offset)
    ]
    return PaperEventListResponse(items=items, limit=limit, offset=offset)


def signal_link_response(
    store: PaperReadStore, source_signal_id: str
) -> PaperSignalLinkResponse:
    orders = store.find_orders_by_signal(source_signal_id)
    if not orders:
        return PaperSignalLinkResponse(
            source_signal_id=source_signal_id,
            linked=False,
            orders=[],
            message="No paper trade linked to this signal",
        )
    return PaperSignalLinkResponse(
        source_signal_id=source_signal_id,
        linked=True,
        orders=[order_item(o) for o in orders],
        message=f"{len(orders)} paper order(s) linked",
    )
