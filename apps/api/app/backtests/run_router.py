"""Controlled backtest run API — POST starts; GET status never executes (Prompt 68C)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from agent.backtest.artifacts import ArtifactError, load_run_payload
from agent.backtest.history_provider import estimate_candle_count
from agent.backtest.limits import (
    RUN_UI_DATA_SOURCES,
    RUN_UI_INTERVALS,
    RUN_UI_MARKET_TYPES,
    RUN_UI_RISK_MODES,
    RUN_UI_SYMBOLS,
)
from apps.api.app.backtests.dependencies import (
    get_backtest_run_results_dir,
    require_backtest_run_local_access,
)
from apps.api.app.backtests.run_schemas import (
    BacktestJobStatusResponse,
    BacktestRunAcceptedResponse,
    BacktestRunCapabilitiesResponse,
    BacktestRunRequest,
)
from apps.api.app.backtests.run_service import (
    LINEAR_LIMITATION,
    RunLimits,
    RunServiceError,
    get_run_service,
)
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.security.operator_local import assert_operator_local_diagnostic

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests-run"])

_MAX_BODY_BYTES = 16_384


def _limits_from_settings(settings: ApiSettings) -> RunLimits:
    return RunLimits(
        max_candles=settings.backtest_max_candles_per_run,
        max_range_ms=settings.backtest_max_range_ms,
        max_simultaneous=settings.backtest_max_simultaneous_runs,
        max_queued=settings.backtest_max_queued_runs,
        max_runtime_seconds=settings.backtest_max_runtime_seconds,
    )


def _map_run_error(exc: RunServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("/run-capabilities", response_model=BacktestRunCapabilitiesResponse)
def run_capabilities(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> BacktestRunCapabilitiesResponse:
    """Advertise supported controls. Loopback when run OR read gate is on."""
    if settings.backtest_run_api_enabled or settings.backtest_read_api_enabled:
        assert_operator_local_diagnostic(request, settings)
    return BacktestRunCapabilitiesResponse(
        run_api_enabled=bool(settings.backtest_run_api_enabled),
        read_api_enabled=bool(settings.backtest_read_api_enabled),
        symbols=sorted(RUN_UI_SYMBOLS),
        market_types=sorted(RUN_UI_MARKET_TYPES),
        intervals=sorted(RUN_UI_INTERVALS, key=lambda x: int(x)),
        risk_modes=sorted(RUN_UI_RISK_MODES),
        data_sources=sorted(RUN_UI_DATA_SOURCES),
        max_candles_per_run=settings.backtest_max_candles_per_run,
        max_range_ms=settings.backtest_max_range_ms,
        max_simultaneous_runs=settings.backtest_max_simultaneous_runs,
        max_queued_runs=settings.backtest_max_queued_runs,
        max_runtime_seconds=settings.backtest_max_runtime_seconds,
    )


@router.post("/runs", response_model=BacktestRunAcceptedResponse)
async def create_run(
    request: Request,
    settings: Annotated[ApiSettings, Depends(require_backtest_run_local_access)],
    results_dir: Annotated[Path, Depends(get_backtest_run_results_dir)],
    idempotency_key_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BacktestRunAcceptedResponse:
    """Explicit operator action to enqueue one isolated historical backtest."""
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype != "application/json":
        raise HTTPException(
            status_code=415,
            detail={"code": "unsupported_media_type", "message": "application/json required"},
        )
    raw = await request.body()
    if len(raw) > _MAX_BODY_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "body_too_large", "message": "request body exceeds 16KiB"},
        )
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_json", "message": "malformed JSON body"},
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_body", "message": "JSON object required"},
        )
    banned = {"dataset_path", "journal_path", "code", "script", "url", "command"}
    if banned.intersection(payload.keys()):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "forbidden_fields",
                "message": "request must not include paths, URLs, or executable fields",
            },
        )
    if idempotency_key_header and not payload.get("idempotency_key"):
        payload["idempotency_key"] = idempotency_key_header.strip()
    try:
        body = BacktestRunRequest.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": str(exc)},
        ) from exc

    service = get_run_service(results_dir, limits=_limits_from_settings(settings))
    try:
        job, replay = service.submit(body)
    except RunServiceError as exc:
        raise _map_run_error(exc) from exc

    est = job.estimated_candles
    if est is None:
        try:
            est = estimate_candle_count(body.start_ms, body.end_ms, body.interval)
        except Exception:  # noqa: BLE001
            est = None

    return BacktestRunAcceptedResponse(
        job_id=job.job_id,
        status=job.status,
        estimated_candles=est,
        idempotent_replay=replay,
    )


@router.get("/jobs/{job_id}", response_model=BacktestJobStatusResponse)
def get_job_status(
    job_id: str,
    settings: Annotated[ApiSettings, Depends(require_backtest_run_local_access)],
    results_dir: Annotated[Path, Depends(get_backtest_run_results_dir)],
) -> BacktestJobStatusResponse:
    """Poll job lifecycle. Never starts or resumes execution."""
    service = get_run_service(results_dir, limits=_limits_from_settings(settings))
    try:
        job = service.get_job(job_id)
    except RunServiceError as exc:
        raise _map_run_error(exc) from exc
    return BacktestJobStatusResponse(**job.to_public())


@router.get("/runs/{run_id}/status", response_model=BacktestJobStatusResponse)
def get_run_status_alias(
    run_id: str,
    settings: Annotated[ApiSettings, Depends(require_backtest_run_local_access)],
    results_dir: Annotated[Path, Depends(get_backtest_run_results_dir)],
) -> BacktestJobStatusResponse:
    """
    Status by job_id (btj_*) or completed run_id (bt_*).

    For bt_* run_ids, synthesizes status from the saved artifact when present.
    GET never starts execution.
    """
    if run_id.startswith("btj_"):
        service = get_run_service(results_dir, limits=_limits_from_settings(settings))
        try:
            job = service.get_job(run_id)
        except RunServiceError as exc:
            raise _map_run_error(exc) from exc
        return BacktestJobStatusResponse(**job.to_public())

    try:
        payload = load_run_payload(results_dir, run_id)
    except ArtifactError as exc:
        raise HTTPException(
            status_code=404 if exc.code in {"run_not_found", "results_missing"} else 400,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    created = int(payload.get("created_ms") or 0)
    ds = payload.get("dataset") or {}
    return BacktestJobStatusResponse(
        job_id=run_id,
        status=str(payload.get("status") or "COMPLETED"),
        run_id=run_id,
        created_ms=created,
        started_ms=created,
        finished_ms=created,
        phase="done",
        request_summary={
            "symbol": ds.get("symbol") if isinstance(ds, dict) else None,
            "market_type": ds.get("market_type") if isinstance(ds, dict) else None,
            "interval": ds.get("interval") if isinstance(ds, dict) else None,
        },
        dataset_hash=ds.get("content_hash") if isinstance(ds, dict) else None,
        result_hash=payload.get("result_hash"),
        linear_limitation=(
            LINEAR_LIMITATION
            if isinstance(ds, dict) and ds.get("market_type") == "linear"
            else None
        ),
    )
