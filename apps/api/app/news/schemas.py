"""Pydantic DTOs for news read API (69A)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NewsDisabledResponse(BaseModel):
    detail: str = "news_read_api_disabled"
    message: str = (
        "News read API is disabled. Set NEWS_READ_API_ENABLED=true for local use."
    )


class NewsStatusResponse(BaseModel):
    enabled: bool
    collection_enabled: bool
    alerts_enabled: bool = False
    llm_enabled: bool = False
    advisory_enabled: bool = False
    schema_version: str
    storage_kind: str = "unknown"
    storage_available: bool = False
    storage_error: str | None = None
    latest_ingestion: dict[str, Any] | None = None
    alert_engine_enabled: bool = False
    auto_collection_enabled: bool = False
    telegram_enabled: bool = False
    scheduler_note: str | None = None
    note: str
    mutations: bool = False
    places_orders: bool = False


class NewsArticleListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class NewsEventListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class NewsEventDetailResponse(BaseModel):
    event: dict[str, Any]


class NewsContextResponse(BaseModel):
    context: dict[str, Any]


class NewsProviderHealthResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class NewsCollectResponse(BaseModel):
    run_id: str
    article_count: int
    event_count: int
    rejected: int
    duplicates_dropped: int
    alerts_created: int = 0
    alerts_suppressed: int = 0
    telegram_confirmed: int = 0
    errors: list[str] = Field(default_factory=list)
    note: str = "Collection complete — advisory storage only; no trading impact"


class NewsAlertListResponse(BaseModel):
    enabled: bool
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    places_orders: bool = False


class NewsUnreadCountResponse(BaseModel):
    enabled: bool
    unread: int
    places_orders: bool = False


class NewsAlertDetailResponse(BaseModel):
    alert: dict[str, Any]
    deliveries: list[dict[str, Any]] = Field(default_factory=list)
    places_orders: bool = False


class NewsAlertSettings(BaseModel):
    min_severity: str = "HIGH"
    symbols: list[str] = Field(default_factory=list)
    cooldown_ms: int = 1_800_000
    ttl_ms: int = 21_600_000
    in_app_enabled: bool = True
    telegram_enabled: bool = False


class NewsAlertSettingsResponse(BaseModel):
    enabled: bool
    settings: NewsAlertSettings
    telegram_configured: bool = False
    places_orders: bool = False
