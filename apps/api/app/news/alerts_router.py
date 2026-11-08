"""Alert read/ack API (Prompt 69B). GET never ingests or sends notifications."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from agent.news.schemas import Severity
from apps.api.app.config import ApiSettings
from apps.api.app.news.dependencies import require_news_local_access
from apps.api.app.news.pg_repository import NewsStorageError
from apps.api.app.news.schemas import (
    NewsAlertDetailResponse,
    NewsAlertListResponse,
    NewsAlertSettings,
    NewsAlertSettingsResponse,
    NewsUnreadCountResponse,
)
from apps.api.app.news.state import get_news_service

router = APIRouter()

_SEVERITIES = {item.value for item in Severity}


def _repo(svc):
    repo = getattr(svc, "alert_repo", None)
    if repo is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "alerts_schema_unavailable",
                "message": "Alert storage is not configured.",
            },
        )
    return repo


def _require_alerts_enabled(settings: ApiSettings) -> None:
    if not settings.news_alerts_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "news_alerts_disabled",
                "message": "Set NEWS_ALERTS_ENABLED=true to change alert state.",
            },
        )


@router.get("/alerts", response_model=NewsAlertListResponse)
def list_alerts(
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    severity: str | None = Query(default=None),
    symbol: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, max_length=32),
) -> NewsAlertListResponse:
    if not settings.news_alerts_enabled:
        return NewsAlertListResponse(enabled=False, items=[], total=0, limit=limit, offset=offset)
    svc = get_news_service()
    repo = _repo(svc)
    if severity and severity not in _SEVERITIES:
        raise HTTPException(status_code=422, detail={"code": "bad_severity", "message": "unknown severity"})
    if status and status not in {"OPEN", "ACKNOWLEDGED", "EXPIRED", "SUPERSEDED"}:
        raise HTTPException(status_code=422, detail={"code": "bad_status", "message": "unknown status"})
    try:
        items = repo.list_alerts(
            limit=limit,
            offset=offset,
            owner_user_id=None,
            severity=severity,
            symbol=symbol,
            status=status,
        )
    except NewsStorageError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    return NewsAlertListResponse(
        enabled=True, items=items, total=len(items) + offset, limit=limit, offset=offset
    )


@router.get("/alerts/unread-count", response_model=NewsUnreadCountResponse)
def unread_count(
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsUnreadCountResponse:
    if not settings.news_alerts_enabled:
        return NewsUnreadCountResponse(enabled=False, unread=0)
    svc = get_news_service()
    repo = _repo(svc)
    try:
        count = int(repo.unread_count(owner_user_id=None))
    except NewsStorageError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    return NewsUnreadCountResponse(enabled=True, unread=count)


@router.get("/alerts/{alert_id}", response_model=NewsAlertDetailResponse)
def get_alert(
    alert_id: str,
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsAlertDetailResponse:
    if not settings.news_alerts_enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "news_alerts_disabled", "message": "Alert engine is disabled."},
        )
    if not alert_id.startswith("nal_") or len(alert_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "bad_alert_id", "message": "invalid alert id"})
    svc = get_news_service()
    repo = _repo(svc)
    try:
        row = repo.get_alert(alert_id, owner_user_id=None)
        deliveries = []
        for key in (f"in_app:{alert_id}", f"telegram:{alert_id}"):
            found = repo.get_delivery(key)
            if found:
                deliveries.append(found)
    except NewsStorageError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    if not row:
        raise HTTPException(status_code=404, detail={"code": "alert_not_found", "message": "unknown alert"})
    return NewsAlertDetailResponse(alert=row, deliveries=deliveries)


@router.post("/alerts/{alert_id}/acknowledge", response_model=NewsAlertDetailResponse)
def acknowledge_alert(
    alert_id: str,
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsAlertDetailResponse:
    _require_alerts_enabled(settings)
    if not alert_id.startswith("nal_") or len(alert_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "bad_alert_id", "message": "invalid alert id"})
    svc = get_news_service()
    repo = _repo(svc)
    try:
        row = repo.acknowledge(alert_id, now_ms=int(time.time() * 1000), owner_user_id=None)
    except NewsStorageError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    if not row:
        raise HTTPException(status_code=404, detail={"code": "alert_not_found", "message": "unknown alert"})
    return NewsAlertDetailResponse(alert=row, deliveries=[])


@router.get("/alert-settings", response_model=NewsAlertSettingsResponse)
def get_settings(
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsAlertSettingsResponse:
    configured = bool(settings.news_telegram_bot_token and settings.news_telegram_chat_id)
    if not settings.news_alerts_enabled:
        return NewsAlertSettingsResponse(
            enabled=False,
            settings=NewsAlertSettings(),
            telegram_configured=configured,
        )
    svc = get_news_service()
    repo = _repo(svc)
    try:
        stored = repo.get_preferences(owner_user_id=None) or {}
    except NewsStorageError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    body = NewsAlertSettings(
        min_severity=str(stored.get("min_severity") or "HIGH"),
        symbols=list(stored.get("symbols") or []),
        cooldown_ms=int(stored.get("cooldown_ms") or 1_800_000),
        ttl_ms=int(stored.get("ttl_ms") or 21_600_000),
        in_app_enabled=bool(stored.get("in_app_enabled", True)),
        telegram_enabled=bool(stored.get("telegram_enabled", False)),
    )
    return NewsAlertSettingsResponse(enabled=True, settings=body, telegram_configured=configured)


@router.put("/alert-settings", response_model=NewsAlertSettingsResponse)
def put_settings(
    payload: NewsAlertSettings,
    settings: Annotated[ApiSettings, Depends(require_news_local_access)],
) -> NewsAlertSettingsResponse:
    _require_alerts_enabled(settings)
    if payload.min_severity not in _SEVERITIES:
        raise HTTPException(status_code=422, detail={"code": "bad_severity", "message": "unknown severity"})
    if not 60_000 <= payload.cooldown_ms <= 86_400_000:
        raise HTTPException(status_code=422, detail={"code": "bad_cooldown", "message": "cooldown out of range"})
    if not 60_000 <= payload.ttl_ms <= 7 * 86_400_000:
        raise HTTPException(status_code=422, detail={"code": "bad_ttl", "message": "ttl out of range"})
    if len(payload.symbols) > 20:
        raise HTTPException(status_code=422, detail={"code": "too_many_symbols", "message": "max 20 symbols"})
    svc = get_news_service()
    repo = _repo(svc)
    stored_in = {
        "min_severity": payload.min_severity,
        "symbols": [s.upper() for s in payload.symbols],
        "cooldown_ms": payload.cooldown_ms,
        "ttl_ms": payload.ttl_ms,
        "in_app_enabled": payload.in_app_enabled,
        "telegram_enabled": payload.telegram_enabled,
        "updated_at_ms": int(time.time() * 1000),
    }
    try:
        stored = repo.save_preferences(stored_in, owner_user_id=None)
    except NewsStorageError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    return NewsAlertSettingsResponse(
        enabled=True,
        settings=NewsAlertSettings(
            min_severity=str(stored.get("min_severity") or payload.min_severity),
            symbols=list(stored.get("symbols") or stored_in["symbols"]),
            cooldown_ms=int(stored.get("cooldown_ms") or payload.cooldown_ms),
            ttl_ms=int(stored.get("ttl_ms") or payload.ttl_ms),
            in_app_enabled=bool(stored.get("in_app_enabled", True)),
            telegram_enabled=bool(stored.get("telegram_enabled", False)),
        ),
        telegram_configured=bool(settings.news_telegram_bot_token and settings.news_telegram_chat_id),
    )
