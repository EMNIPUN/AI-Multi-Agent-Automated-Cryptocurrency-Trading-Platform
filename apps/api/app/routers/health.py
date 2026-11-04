"""Liveness probe — no secrets, no exchange calls, no database requirement."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api import __version__
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: ApiSettings = Depends(get_api_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version or __version__,
    )
