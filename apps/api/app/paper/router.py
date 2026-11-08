"""Read-only paper trading FastAPI routes — no mutations, no broker auto-attach."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agent.paper.analytics.service import AnalyticsError, compute_session_analytics
from agent.paper.analytics.service import list_equity_points as analytics_equity_points
from agent.paper.analytics.service import list_trade_metrics as analytics_trade_metrics
from agent.paper.integration import PAPER_BROKER_AUTO_ATTACH
from agent.paper.read_store import PaperDbUnavailable, PaperReadStore
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.paper.analytics_serialize import (
    serialize_analytics,
    serialize_equity_point,
    serialize_trade,
)
from apps.api.app.paper.dependencies import (
    get_paper_read_store,
    paper_db_path,
)
from apps.api.app.paper.schemas import (
    PaperAccountResponse,
    PaperAnalyticsEquityResponse,
    PaperAnalyticsResponse,
    PaperAnalyticsSymbolsResponse,
    PaperAnalyticsTradesResponse,
    PaperDisabledResponse,
    PaperEventListResponse,
    PaperFillListResponse,
    PaperOrderListResponse,
    PaperPositionListResponse,
    PaperSessionListResponse,
    PaperSessionSummary,
    PaperSignalLinkResponse,
    PaperStatusResponse,
)
from apps.api.app.paper.service import (
    account_response,
    build_status,
    list_events_response,
    list_fills_response,
    list_orders_response,
    list_positions_response,
    list_sessions_response,
    session_summary,
    signal_link_response,
    validate_session_id,
    validate_signal_id,
    validate_symbol,
)
from apps.api.app.security.operator_local import assert_operator_local_diagnostic

router = APIRouter(prefix="/api/v1/paper", tags=["paper-read"])


def _pagination(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, 100)), max(0, offset)


def _require_session(store: PaperReadStore, session_id: str):
    try:
        sid = validate_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not store.exists():
        raise HTTPException(status_code=404, detail="session_not_found")
    try:
        sess = store.get_session(sid)
    except PaperDbUnavailable as exc:
        raise HTTPException(status_code=500, detail="paper_db_error") from exc
    if sess is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return sess


@router.get("/status", response_model=PaperStatusResponse)
def paper_status(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    db_path: Annotated[Any, Depends(paper_db_path)],
) -> PaperStatusResponse:
    """Always available. When enabled, loopback-only; never opens DB when disabled."""
    if not settings.paper_read_api_enabled:
        return build_status(enabled=False, db_path=db_path)
    assert_operator_local_diagnostic(request, settings)
    return build_status(enabled=True, db_path=db_path)


@router.get("/sessions", response_model=PaperSessionListResponse)
def list_sessions(
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaperSessionListResponse:
    lim, off = _pagination(limit, offset)
    if not store.exists():
        return PaperSessionListResponse(items=[], total=0, limit=lim, offset=off)
    try:
        return list_sessions_response(store, limit=lim, offset=off)
    except PaperDbUnavailable as exc:
        raise HTTPException(status_code=500, detail="paper_db_error") from exc


@router.get("/sessions/{session_id}", response_model=PaperSessionSummary)
def get_session(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
) -> PaperSessionSummary:
    sess = _require_session(store, session_id)
    return session_summary(sess, store.count_open_positions(sess.session_id))


@router.get("/sessions/{session_id}/account", response_model=PaperAccountResponse)
def get_account(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
) -> PaperAccountResponse:
    sess = _require_session(store, session_id)
    return account_response(store, sess)


@router.get("/sessions/{session_id}/positions", response_model=PaperPositionListResponse)
def get_positions(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaperPositionListResponse:
    sess = _require_session(store, session_id)
    lim, off = _pagination(limit, offset)
    try:
        sym = validate_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    st = status.strip().upper() if status else None
    if st is not None and st not in {"OPEN", "CLOSED"}:
        raise HTTPException(status_code=400, detail="invalid_position_status")
    return list_positions_response(
        store, sess.session_id, status=st, symbol=sym, limit=lim, offset=off
    )


@router.get("/sessions/{session_id}/orders", response_model=PaperOrderListResponse)
def get_orders(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    source_signal_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaperOrderListResponse:
    sess = _require_session(store, session_id)
    lim, off = _pagination(limit, offset)
    try:
        sym = validate_symbol(symbol)
        sig = validate_signal_id(source_signal_id) if source_signal_id else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    st = status.strip().upper() if status else None
    if st is not None and st not in {"PENDING", "FILLED", "REJECTED", "CANCELLED"}:
        raise HTTPException(status_code=400, detail="invalid_order_status")
    return list_orders_response(
        store,
        sess.session_id,
        status=st,
        symbol=sym,
        source_signal_id=sig,
        limit=lim,
        offset=off,
    )


@router.get("/sessions/{session_id}/fills", response_model=PaperFillListResponse)
def get_fills(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaperFillListResponse:
    sess = _require_session(store, session_id)
    lim, off = _pagination(limit, offset)
    try:
        sym = validate_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return list_fills_response(
        store, sess.session_id, symbol=sym, limit=lim, offset=off
    )


@router.get("/sessions/{session_id}/events", response_model=PaperEventListResponse)
def get_events(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaperEventListResponse:
    sess = _require_session(store, session_id)
    lim, off = _pagination(limit, offset)
    return list_events_response(store, sess.session_id, limit=lim, offset=off)


@router.get(
    "/sessions/{session_id}/analytics",
    response_model=PaperAnalyticsResponse,
)
def session_analytics(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    symbol: str | None = Query(default=None),
    exit_from_ms: int | None = Query(default=None, ge=0),
    exit_to_ms: int | None = Query(default=None, ge=0),
) -> PaperAnalyticsResponse:
    _require_session(store, session_id)
    try:
        sym = validate_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = compute_session_analytics(
            store,
            session_id,
            symbol=sym,
            exit_from_ms=exit_from_ms,
            exit_to_ms=exit_to_ms,
        )
    except AnalyticsError as exc:
        code = 404 if exc.code == "session_not_found" else 500
        raise HTTPException(status_code=code, detail=exc.code) from exc
    return serialize_analytics(result)


@router.get(
    "/sessions/{session_id}/analytics/trades",
    response_model=PaperAnalyticsTradesResponse,
)
def session_analytics_trades(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    symbol: str | None = Query(default=None),
    exit_from_ms: int | None = Query(default=None, ge=0),
    exit_to_ms: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaperAnalyticsTradesResponse:
    _require_session(store, session_id)
    try:
        sym = validate_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    lim, off = _pagination(limit, offset)
    try:
        trades, warnings = analytics_trade_metrics(
            store,
            session_id,
            symbol=sym,
            exit_from_ms=exit_from_ms,
            exit_to_ms=exit_to_ms,
            limit=lim,
            offset=off,
        )
    except AnalyticsError as exc:
        code = 404 if exc.code == "session_not_found" else 500
        raise HTTPException(status_code=code, detail=exc.code) from exc
    return PaperAnalyticsTradesResponse(
        items=[serialize_trade(t) for t in trades],
        limit=lim,
        offset=off,
        warnings=warnings,
    )


@router.get(
    "/sessions/{session_id}/analytics/equity",
    response_model=PaperAnalyticsEquityResponse,
)
def session_analytics_equity(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    series: str = Query(default="marked", pattern="^(marked|realized_balance)$"),
    from_ms: int | None = Query(default=None, ge=0),
    to_ms: int | None = Query(default=None, ge=0),
) -> PaperAnalyticsEquityResponse:
    _require_session(store, session_id)
    try:
        points, warnings = analytics_equity_points(
            store,
            session_id,
            series=series,
            from_ms=from_ms,
            to_ms=to_ms,
        )
    except AnalyticsError as exc:
        code = 404 if exc.code == "session_not_found" else 500
        raise HTTPException(status_code=code, detail=exc.code) from exc
    return PaperAnalyticsEquityResponse(
        series_type=series if series == "realized_balance" else "marked_equity",
        points=[serialize_equity_point(p) for p in points],
        warnings=warnings,
    )


@router.get(
    "/sessions/{session_id}/analytics/symbols",
    response_model=PaperAnalyticsSymbolsResponse,
)
def session_analytics_symbols(
    session_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
    exit_from_ms: int | None = Query(default=None, ge=0),
    exit_to_ms: int | None = Query(default=None, ge=0),
) -> PaperAnalyticsSymbolsResponse:
    _require_session(store, session_id)
    try:
        result = compute_session_analytics(
            store,
            session_id,
            exit_from_ms=exit_from_ms,
            exit_to_ms=exit_to_ms,
        )
    except AnalyticsError as exc:
        code = 404 if exc.code == "session_not_found" else 500
        raise HTTPException(status_code=code, detail=exc.code) from exc
    payload = serialize_analytics(result)
    return PaperAnalyticsSymbolsResponse(items=payload.symbol_breakdown)


@router.get("/orders/by-signal/{signal_id}", response_model=PaperSignalLinkResponse)
def orders_by_signal(
    signal_id: str,
    store: Annotated[PaperReadStore, Depends(get_paper_read_store)],
) -> PaperSignalLinkResponse:
    """Lookup paper orders linked to a persisted signal — never creates trades."""
    try:
        sid = validate_signal_id(signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not store.exists():
        return PaperSignalLinkResponse(
            source_signal_id=sid,
            linked=False,
            orders=[],
            message="No paper trade linked to this signal",
        )
    try:
        return signal_link_response(store, sid)
    except PaperDbUnavailable as exc:
        raise HTTPException(status_code=500, detail="paper_db_error") from exc


@router.get("/disabled-probe", include_in_schema=False)
def disabled_probe(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    """Internal helper for tests — confirms gate without requiring loopback write."""
    return {
        "paper_read_api_enabled": settings.paper_read_api_enabled,
        "broker_auto_attach": PAPER_BROKER_AUTO_ATTACH,
        "trading_endpoints": False,
        "detail": (
            PaperDisabledResponse().detail
            if not settings.paper_read_api_enabled
            else "enabled"
        ),
    }
