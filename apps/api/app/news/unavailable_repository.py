"""Fail-closed repository — raises on every persistence/read call."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from agent.news.schemas import ClassifiedEvent, ValidatedArticle
from apps.api.app.news.pg_repository import NewsStorageError


class UnavailableNewsRepository:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def storage_kind(self) -> str:
        return "unavailable"

    def ping(self) -> bool:
        return False

    def _raise(self) -> None:
        raise NewsStorageError("storage_unavailable", self.reason)

    def upsert_source(self, *, provider_id: str, name: str, kind: str, meta: dict[str, Any]) -> None:
        self._raise()

    def upsert_article(self, article: ValidatedArticle, *, owner_user_id: UUID | None) -> None:
        self._raise()

    def upsert_event(self, event: ClassifiedEvent, *, owner_user_id: UUID | None) -> None:
        self._raise()

    def record_ingestion_run(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None:
        self._raise()

    def record_provider_health(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None:
        self._raise()

    def list_articles(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]:
        self._raise()
        return []

    def list_events(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]:
        self._raise()
        return []

    def get_event(self, event_id: str, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        self._raise()
        return None

    def list_events_for_symbol(
        self, symbol: str, *, limit: int, owner_user_id: UUID | None
    ) -> list[dict[str, Any]]:
        self._raise()
        return []

    def latest_ingestion(self, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        self._raise()
        return None
