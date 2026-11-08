"""News API feature gates + loopback access."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.news.schemas import NewsDisabledResponse
from apps.api.app.security.operator_local import assert_operator_local_diagnostic


def require_news_read_enabled(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> ApiSettings:
    if not settings.news_read_api_enabled:
        raise HTTPException(
            status_code=503,
            detail=NewsDisabledResponse().model_dump(),
        )
    return settings


def require_news_local_access(
    request: Request,
    settings: Annotated[ApiSettings, Depends(require_news_read_enabled)],
) -> ApiSettings:
    assert_operator_local_diagnostic(request, settings)
    return settings


def require_news_collection_enabled(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> ApiSettings:
    if not settings.news_collection_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "news_collection_disabled",
                "message": "Set NEWS_COLLECTION_ENABLED=true to run ingestion.",
            },
        )
    assert_operator_local_diagnostic(request, settings)
    return settings
