"""Read-only news API + gated collection (Prompt 69A.1). No trading side effects."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agent.news.config import NEWS_SCHEMA_VERSION, NewsConfig
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.news.dependencies import (
    require_news_collection_enabled,
    require_news_local_access,
)
from apps.api.app.news.pg_repository import NewsStorageError
from apps.api.app.news.schemas import (
    NewsArticleListResponse,
    NewsCollectResponse,
    NewsContextResponse,
    NewsEventDetailResponse,
    NewsEventListResponse,
    NewsProviderHealthResponse,
    NewsStatusResponse,
)
from apps.api.app.news.alerts_router import router as alerts_router
from apps.api.app.news.state import get_news_service
from apps.api.app.security.operator_local import assert_operator_local_diagnostic

router = APIRouter(prefix="/api/v1/news", tags=["news"])
router.include_router(alerts_router)


def _page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, 100)), max(0, offset)


def _news_config(settings: ApiSettings) -> NewsConfig:
    return NewsConfig(
        collection_enabled=settings.news_collection_enabled,
        read_api_enabled=settings.news_read_api_enabled,
        alerts_enabled=settings.news_alerts_enabled,
        llm_enabled=settings.news_llm_enabled,
        advisory_enabled=settings.news_agent_advisory_enabled,
        newsdata_api_key=settings.newsdata_api_key,
        rss_feed_urls=tuple(
            u.strip() for u in (settings.news_rss_feed_urls or "").split(",") if u.strip()
        ),
        telegram_enabled=settings.news_telegram_enabled,
        telegram_bot_token=settings.news_telegram_bot_token,
        telegram_chat_id=settings.news_telegram_chat_id,
        auto_collection_enabled=settings.news_auto_collection_enabled,
        collection_interval_seconds=max(60, int(settings.news_collection_interval_seconds or 900)),
    )


def _require_storage(svc) -> None:
    if not svc.storage_available:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "storage_unavailable",
                "message": svc.storage_error or "Supabase news storage unavailable",
            },
        )


@router.get("/status", response_model=NewsStatusResponse)
def news_status(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> NewsStatusResponse:
    if settings.news_read_api_enabled:
        assert_operator_local_diagnostic(request, settings)
    svc = get_news_service(
        _news_config(settings)
    )
    body = svc.status()
    return NewsStatusResponse(
        enabled=bool(settings.news_read_api_enabled),
        collection_enabled=bool(settings.news_collection_enabled),
        alerts_enabled=bool(settings.news_alerts_enabled),
        llm_enabled=bool(settings.news_llm_enabled),
        advisory_enabled=bool(settings.news_agent_advisory_enabled),
        schema_version=NEWS_SCHEMA_VERSION,
        storage_kind=str(body.get("storage_kind") or "unknown"),
        storage_available=bool(body.get("storage_available")),
        storage_error=body.get("storage_error"),
        latest_ingestion=body.get("latest_ingestion") if body.get("storage_available") else None,
        alert_engine_enabled=bool(body.get("alert_engine_enabled")),
        auto_collection_enabled=bool(body.get("auto_collection_enabled")),
        telegram_enabled=bool(body.get("telegram_enabled")),
        scheduler_note=(
            "Manual collection only. Automatic polling stays off until "
            "NEWS_AUTO_COLLECTION_ENABLED=true and migration 20261108_0008 is applied. "
            "Provider feeds are delayed, not realtime."
        ),
        note=str(body.get("note") or ""),
        mutations=False,
        places_orders=False,
    )


@router.get("/articles", response_model=NewsArticleListResponse)
def list_articles(
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NewsArticleListResponse:
    lim, off = _page(limit, offset)
    svc = get_news_service()
    _require_storage(svc)
    try:
        items = svc.repo.list_articles(limit=lim, offset=off, owner_user_id=None)
    except NewsStorageError as exc:
        raise HTTPException(
            status_code=503, detail={"code": exc.code, "message": exc.message}
        ) from exc
    return NewsArticleListResponse(items=items, total=len(items) + off, limit=lim, offset=off)


@router.get("/events", response_model=NewsEventListResponse)
def list_events(
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NewsEventListResponse:
    lim, off = _page(limit, offset)
    svc = get_news_service()
    _require_storage(svc)
    try:
        items = svc.repo.list_events(limit=lim, offset=off, owner_user_id=None)
    except NewsStorageError as exc:
        raise HTTPException(
            status_code=503, detail={"code": exc.code, "message": exc.message}
        ) from exc
    return NewsEventListResponse(items=items, total=len(items) + off, limit=lim, offset=off)


@router.get("/events/{event_id}", response_model=NewsEventDetailResponse)
def get_event(
    event_id: str,
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsEventDetailResponse:
    svc = get_news_service()
    _require_storage(svc)
    try:
        row = svc.repo.get_event(event_id, owner_user_id=None)
    except NewsStorageError as exc:
        raise HTTPException(
            status_code=503, detail={"code": exc.code, "message": exc.message}
        ) from exc
    if not row:
        raise HTTPException(
            status_code=404, detail={"code": "event_not_found", "message": "unknown event"}
        )
    return NewsEventDetailResponse(event=row)


@router.get("/context/{symbol}", response_model=NewsContextResponse)
def get_context(
    symbol: str,
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsContextResponse:
    svc = get_news_service()
    _require_storage(svc)
    return NewsContextResponse(context=svc.context_for_symbol(symbol))


@router.get("/providers/health", response_model=NewsProviderHealthResponse)
def provider_health(
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsProviderHealthResponse:
    svc = get_news_service()
    _require_storage(svc)
    list_fn = getattr(svc.repo, "list_provider_health", None)
    if callable(list_fn):
        items = list_fn(limit=50)
    else:
        items = list(getattr(svc.repo, "health", []) or [])[-50:]
    return NewsProviderHealthResponse(items=items)


@router.post("/collect", response_model=NewsCollectResponse)
def collect_now(
    settings: Annotated[ApiSettings, Depends(require_news_collection_enabled)],
) -> NewsCollectResponse:
    """Loopback-only explicit collection. Never auto-runs on GET. Requires Supabase."""
    cfg = _news_config(settings)
    cfg = NewsConfig(
        collection_enabled=True,
        read_api_enabled=cfg.read_api_enabled,
        alerts_enabled=cfg.alerts_enabled,
        llm_enabled=False,
        advisory_enabled=False,
        newsdata_api_key=cfg.newsdata_api_key,
        rss_feed_urls=cfg.rss_feed_urls,
        telegram_enabled=cfg.telegram_enabled,
        telegram_bot_token=cfg.telegram_bot_token,
        telegram_chat_id=cfg.telegram_chat_id,
        auto_collection_enabled=cfg.auto_collection_enabled,
        collection_interval_seconds=cfg.collection_interval_seconds,
        alert_min_severity=cfg.alert_min_severity,
        alert_cooldown_ms=cfg.alert_cooldown_ms,
        alert_ttl_ms=cfg.alert_ttl_ms,
    )
    svc = get_news_service(cfg)
    svc.config = cfg
    _bind_telegram(svc, settings)
    _require_storage(svc)
    try:
        result = svc.run_collection()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail={
                "code": "collection_not_persisted",
                "message": str(exc),
            },
        ) from exc
    return NewsCollectResponse(
        run_id=result.run_id,
        article_count=len(result.articles),
        event_count=len(result.events),
        rejected=result.rejected,
        duplicates_dropped=result.duplicates_dropped,
        alerts_created=result.alerts_created,
        alerts_suppressed=result.alerts_suppressed,
        telegram_confirmed=result.telegram_confirmed,
        errors=list(result.errors),
    )


def _bind_telegram(svc, settings: ApiSettings) -> None:
    from agent.news.alerts.telegram import TelegramNotifier

    if not settings.news_telegram_enabled:
        svc.telegram = None
        return
    svc.telegram = TelegramNotifier(
        enabled=True,
        token=settings.news_telegram_bot_token,
        chat_id=settings.news_telegram_chat_id,
    )
