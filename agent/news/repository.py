"""News persistence — in-memory for tests; SQLAlchemy Postgres for Supabase SoT."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any, Protocol
from uuid import UUID

from agent.news.schemas import ClassifiedEvent, ValidatedArticle


class NewsRepository(Protocol):
    def storage_kind(self) -> str: ...

    def ping(self) -> bool: ...

    def upsert_source(self, *, provider_id: str, name: str, kind: str, meta: dict[str, Any]) -> None: ...

    def upsert_article(self, article: ValidatedArticle, *, owner_user_id: UUID | None) -> None: ...

    def upsert_event(self, event: ClassifiedEvent, *, owner_user_id: UUID | None) -> None: ...

    def record_ingestion_run(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None: ...

    def record_provider_health(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None: ...

    def list_articles(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]: ...

    def list_events(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]: ...

    def get_event(self, event_id: str, *, owner_user_id: UUID | None) -> dict[str, Any] | None: ...

    def list_events_for_symbol(
        self, symbol: str, *, limit: int, owner_user_id: UUID | None
    ) -> list[dict[str, Any]]: ...

    def latest_ingestion(self, *, owner_user_id: UUID | None) -> dict[str, Any] | None: ...


class InMemoryNewsRepository:
    """Process-local store for isolated unit tests ONLY — never production runtime."""

    def __init__(self) -> None:
        self.sources: dict[str, dict[str, Any]] = {}
        self.articles: dict[str, dict[str, Any]] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self.runs: list[dict[str, Any]] = []
        self.health: list[dict[str, Any]] = []

    def storage_kind(self) -> str:
        return "memory_test_only"

    def ping(self) -> bool:
        return True

    def upsert_source(self, *, provider_id: str, name: str, kind: str, meta: dict[str, Any]) -> None:
        self.sources[provider_id] = {
            "provider_id": provider_id,
            "name": name,
            "kind": kind,
            "meta": meta,
            "updated_ms": int(time.time() * 1000),
        }

    def upsert_article(self, article: ValidatedArticle, *, owner_user_id: UUID | None) -> None:
        self.articles[article.content_hash] = {
            **asdict(article),
            "asset_hints": list(article.asset_hints),
            "owner_user_id": str(owner_user_id) if owner_user_id else None,
        }

    def upsert_event(self, event: ClassifiedEvent, *, owner_user_id: UUID | None) -> None:
        self.events[event.event_id] = {
            "event_id": event.event_id,
            "category": event.category.value,
            "severity": event.severity.value,
            "sentiment": event.sentiment.value,
            "verification": event.verification.value,
            "headline": event.headline,
            "summary": event.summary,
            "assets": list(event.assets),
            "article_content_hashes": list(event.article_content_hashes),
            "published_at_ms": event.published_at_ms,
            "first_observed_at_ms": event.first_observed_at_ms,
            "available_at_ms": event.available_at_ms,
            "classification_at_ms": event.classification_at_ms,
            "reason_codes": list(event.reason_codes),
            "warnings": list(event.warnings),
            "evidence_quality": event.evidence_quality,
            "owner_user_id": str(owner_user_id) if owner_user_id else None,
        }

    def record_ingestion_run(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None:
        row = dict(payload)
        row["owner_user_id"] = str(owner_user_id) if owner_user_id else None
        self.runs.append(row)

    def record_provider_health(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None:
        row = dict(payload)
        row["owner_user_id"] = str(owner_user_id) if owner_user_id else None
        self.health.append(row)

    def list_articles(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]:
        rows = list(self.articles.values())
        rows.sort(key=lambda r: int(r.get("ingested_at_ms") or 0), reverse=True)
        return rows[offset : offset + limit]

    def list_events(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]:
        rows = list(self.events.values())
        rows.sort(key=lambda r: int(r.get("available_at_ms") or 0), reverse=True)
        return rows[offset : offset + limit]

    def get_event(self, event_id: str, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        return self.events.get(event_id)

    def list_events_for_symbol(
        self, symbol: str, *, limit: int, owner_user_id: UUID | None
    ) -> list[dict[str, Any]]:
        sym = symbol.upper()
        rows = [e for e in self.events.values() if sym in (e.get("assets") or [])]
        rows.sort(key=lambda r: int(r.get("available_at_ms") or 0), reverse=True)
        return rows[:limit]

    def latest_ingestion(self, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        return self.runs[-1] if self.runs else None


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)
