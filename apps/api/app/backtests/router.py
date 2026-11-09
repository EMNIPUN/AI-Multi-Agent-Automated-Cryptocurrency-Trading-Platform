"""Read-only FastAPI routes for saved 68A backtest artifacts — no execution."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agent.backtest.artifacts import ArtifactError
from apps.api.app.backtests.dependencies import (
    backtest_results_dir_ungated,
    get_backtest_results_dir,
)
from apps.api.app.backtests.schemas import (
    BacktestDecisionsResponse,
    BacktestEquityResponse,
    BacktestMetricsResponse,
    BacktestOrdersResponse,
    BacktestRunDetailResponse,
    BacktestRunListResponse,
    BacktestStatusResponse,
    BacktestTradesResponse,
)
from apps.api.app.backtests.service import (
    build_status,
    list_runs,
    run_decisions,
    run_detail,
    run_equity,
    run_metrics,
    run_orders,
    run_trades,
)
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.security.operator_local import assert_operator_local_diagnostic

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests-read"])


def _pagination(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, 100)), max(0, offset)


def _map_artifact_error(exc: ArtifactError) -> HTTPException:
    code = exc.code
    if code in {"invalid_run_id", "path_escape", "symlink_escape", "run_id_mismatch"}:
        status = 400 if code == "invalid_run_id" else 400
        if code == "invalid_run_id":
            status = 400
        elif code in {"path_escape", "symlink_escape"}:
            status = 400
        return HTTPException(status_code=status, detail={"code": code, "message": exc.message})
    if code in {"run_not_found", "results_missing"}:
        return HTTPException(status_code=404, detail={"code": code, "message": exc.message})
    if code in {"corrupt_json", "empty_artifact", "invalid_artifact", "artifact_too_large"}:
        return HTTPException(status_code=422, detail={"code": code, "message": exc.message})
    return HTTPException(status_code=500, detail={"code": code, "message": exc.message})


@router.get("/status", response_model=BacktestStatusResponse)
def backtest_status(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    results_dir: Annotated[Path, Depends(backtest_results_dir_ungated)],
) -> BacktestStatusResponse:
    """Always available. When enabled, loopback-only; never creates directories when disabled."""
    if not settings.backtest_read_api_enabled:
        return build_status(
            enabled=False,
            results_dir=results_dir,
            run_api_enabled=bool(settings.backtest_run_api_enabled),
        )
    assert_operator_local_diagnostic(request, settings)
    return build_status(
        enabled=True,
        results_dir=results_dir,
        run_api_enabled=bool(settings.backtest_run_api_enabled),
    )


@router.get("/runs", response_model=BacktestRunListResponse)
def get_runs(
    results_dir: Annotated[Path, Depends(get_backtest_results_dir)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BacktestRunListResponse:
    lim, off = _pagination(limit, offset)
    if not results_dir.exists():
        return BacktestRunListResponse(items=[], total=0, limit=lim, offset=off)
    try:
        return list_runs(results_dir, limit=lim, offset=off)
    except ArtifactError as exc:
        raise _map_artifact_error(exc) from exc


@router.get("/runs/{run_id}", response_model=BacktestRunDetailResponse)
def get_run(
    run_id: str,
    results_dir: Annotated[Path, Depends(get_backtest_results_dir)],
) -> BacktestRunDetailResponse:
    try:
        return run_detail(results_dir, run_id)
    except ArtifactError as exc:
        raise _map_artifact_error(exc) from exc


@router.get("/runs/{run_id}/metrics", response_model=BacktestMetricsResponse)
def get_metrics(
    run_id: str,
    results_dir: Annotated[Path, Depends(get_backtest_results_dir)],
) -> BacktestMetricsResponse:
    try:
        return run_metrics(results_dir, run_id)
    except ArtifactError as exc:
        raise _map_artifact_error(exc) from exc


@router.get("/runs/{run_id}/trades", response_model=BacktestTradesResponse)
def get_trades(
    run_id: str,
    results_dir: Annotated[Path, Depends(get_backtest_results_dir)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BacktestTradesResponse:
    lim, off = _pagination(limit, offset)
    try:
        return run_trades(results_dir, run_id, limit=lim, offset=off)
    except ArtifactError as exc:
        raise _map_artifact_error(exc) from exc


@router.get("/runs/{run_id}/equity", response_model=BacktestEquityResponse)
def get_equity(
    run_id: str,
    results_dir: Annotated[Path, Depends(get_backtest_results_dir)],
) -> BacktestEquityResponse:
    try:
        return run_equity(results_dir, run_id)
    except ArtifactError as exc:
        raise _map_artifact_error(exc) from exc


@router.get("/runs/{run_id}/decisions", response_model=BacktestDecisionsResponse)
def get_decisions(
    run_id: str,
    results_dir: Annotated[Path, Depends(get_backtest_results_dir)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BacktestDecisionsResponse:
    lim, off = _pagination(limit, offset)
    try:
        return run_decisions(results_dir, run_id, limit=lim, offset=off)
    except ArtifactError as exc:
        raise _map_artifact_error(exc) from exc


@router.get("/runs/{run_id}/orders", response_model=BacktestOrdersResponse)
def get_orders(
    run_id: str,
    results_dir: Annotated[Path, Depends(get_backtest_results_dir)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BacktestOrdersResponse:
    lim, off = _pagination(limit, offset)
    try:
        return run_orders(results_dir, run_id, limit=lim, offset=off)
    except ArtifactError as exc:
        raise _map_artifact_error(exc) from exc


_NEWS_MIGRATION_CHAIN = (
    "20261108_0008",
    "20261108_0009",
    "20261108_0010",
    "20261108_0011",
)


def _live_alembic_revision() -> str | None:
    """Read-only revision probe. Never logs a connection string."""
    try:
        from sqlalchemy import text

        from apps.api.app.db import create_db_engine

        engine = create_db_engine()
        try:
            with engine.connect() as conn:
                value = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
            return str(value) if value else None
        finally:
            engine.dispose()
    except Exception:
        return None


@router.get("/shadow-status")
def shadow_status(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict:
    """Read-only provenance gate. Does not run a backtest or call a model."""
    if settings.backtest_read_api_enabled:
        assert_operator_local_diagnostic(request, settings)
    revision = _live_alembic_revision()
    if revision is None:
        pending = list(_NEWS_MIGRATION_CHAIN)
        probe = "unavailable"
        durable = False
    else:
        pending = [item for item in _NEWS_MIGRATION_CHAIN if item > revision]
        probe = "ok"
        durable = revision >= "20261108_0011"
    return {
        "enabled": bool(settings.backtest_read_api_enabled),
        "historical_news_backtest_valid": False,
        "provenance_status": "incomplete",
        "migrations_pending": pending,
        "last_verified_development_revision": revision,
        "revision_probe": probe,
        "openai_called": False,
        "llm_budget_durable_across_processes": durable,
        "research_policies_activated": False,
        "decisions_unchanged": True,
        "labels": [
            "Historical Simulation — Not Live Trading",
            "Advisory Only — Trading Decisions Unchanged",
        ],
        "note": (
            "Events stored before revision archiving have no reconstructed history. "
            "historical_news_backtest_valid stays false until an archive is complete "
            "for the requested window."
        ),
    }

