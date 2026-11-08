"""Backtest read/run API dependencies — feature gates + loopback diagnostic access."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from apps.api.app.backtests.run_schemas import BacktestRunDisabledResponse
from apps.api.app.backtests.schemas import BacktestDisabledResponse
from apps.api.app.backtests.service import resolve_results_dir
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.security.operator_local import assert_operator_local_diagnostic


def require_backtest_read_enabled(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> ApiSettings:
    if not settings.backtest_read_api_enabled:
        raise HTTPException(
            status_code=503,
            detail=BacktestDisabledResponse().model_dump(),
        )
    return settings


def require_backtest_local_access(
    request: Request,
    settings: Annotated[ApiSettings, Depends(require_backtest_read_enabled)],
) -> ApiSettings:
    """Same loopback/operator diagnostic gate as paper read API."""
    assert_operator_local_diagnostic(request, settings)
    return settings


def get_backtest_results_dir(
    settings: Annotated[ApiSettings, Depends(require_backtest_local_access)],
) -> Path:
    return resolve_results_dir(settings.backtest_results_dir)


def backtest_results_dir_ungated(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> Path:
    return resolve_results_dir(settings.backtest_results_dir)


def require_backtest_run_enabled(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> ApiSettings:
    if not settings.backtest_run_api_enabled:
        raise HTTPException(
            status_code=503,
            detail=BacktestRunDisabledResponse().model_dump(),
        )
    return settings


def require_backtest_run_local_access(
    request: Request,
    settings: Annotated[ApiSettings, Depends(require_backtest_run_enabled)],
) -> ApiSettings:
    """Loopback-only gate for state-changing backtest run endpoints."""
    assert_operator_local_diagnostic(request, settings)
    return settings


def get_backtest_run_results_dir(
    settings: Annotated[ApiSettings, Depends(require_backtest_run_local_access)],
) -> Path:
    return resolve_results_dir(settings.backtest_results_dir)
