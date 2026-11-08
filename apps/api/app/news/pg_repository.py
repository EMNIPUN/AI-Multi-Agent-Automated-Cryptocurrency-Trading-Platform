"""
Supabase PostgreSQL news repository (Prompt 69A.1).

Never falls back to SQLite or in-memory. Fail closed on connectivity/schema errors.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from agent.news.schemas import ClassifiedEvent, ValidatedArticle
from apps.api.app.persistence.news_models import (
    NewsArticleRow,
    NewsClassificationRow,
    NewsEventAssetRow,
    NewsEventRow,
    NewsIngestionRunRow,
    NewsProviderHealthRow,
    NewsSourceRow,
)


class NewsStorageError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PostgresNewsRepository:
    """Durable news SoT on Postgres (Supabase)."""

    def __init__(self, engine: Engine) -> None:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            raise NewsStorageError(
                "sqlite_forbidden",
                "News persistence must not use SQLite — configure DATABASE_URL Postgres.",
            )
        if dialect not in {"postgresql", "postgres"}:
            raise NewsStorageError(
                "unsupported_dialect",
                f"News persistence requires PostgreSQL, got {dialect}",
            )
        self._engine = engine
        self._Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def storage_kind(self) -> str:
        return "supabase_postgres"

    def ping(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                # Fail closed if foundation table missing.
                conn.execute(text("SELECT 1 FROM app.news_articles LIMIT 1"))
            return True
        except SQLAlchemyError:
            return False

    def require_ready(self) -> None:
        if not self.ping():
            raise NewsStorageError(
                "storage_unavailable",
                "Supabase news tables unreachable — apply migration 20261108_0007 and check DATABASE_URL.",
            )

    def _session(self) -> Session:
        return self._Session()

    def upsert_source(self, *, provider_id: str, name: str, kind: str, meta: dict[str, Any]) -> None:
        self.require_ready()
        with self._session() as session:
            try:
                self._upsert_source(session, provider_id=provider_id, name=name, kind=kind, meta=meta)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"source upsert failed: {exc}") from exc

    def upsert_article(self, article: ValidatedArticle, *, owner_user_id: UUID | None) -> None:
        self.require_ready()
        with self._session() as session:
            try:
                self._upsert_article(session, article, owner_user_id=owner_user_id)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"article upsert failed: {exc}") from exc

    def upsert_event(self, event: ClassifiedEvent, *, owner_user_id: UUID | None) -> None:
        self.require_ready()
        with self._session() as session:
            try:
                self._upsert_event(session, event, owner_user_id=owner_user_id)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"event upsert failed: {exc}") from exc

    def record_ingestion_run(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None:
        self.require_ready()
        with self._session() as session:
            try:
                self._record_run(session, payload, owner_user_id=owner_user_id)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"ingestion run failed: {exc}") from exc

    def record_provider_health(self, payload: dict[str, Any], *, owner_user_id: UUID | None) -> None:
        self.require_ready()
        with self._session() as session:
            try:
                self._record_health(session, payload, owner_user_id=owner_user_id)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"health write failed: {exc}") from exc

    def persist_collection(
        self,
        *,
        provider_ids: list[str],
        articles: list[ValidatedArticle],
        events: list[ClassifiedEvent],
        health_rows: list[dict[str, Any]],
        run_payload: dict[str, Any],
        owner_user_id: UUID | None,
    ) -> None:
        """Single transaction for a collection run — all-or-nothing."""
        self.require_ready()
        with self._session() as session:
            try:
                for pid in provider_ids:
                    self._upsert_source(
                        session,
                        provider_id=pid,
                        name=pid,
                        kind="provider",
                        meta={"schema": run_payload.get("schema_version")},
                    )
                for h in health_rows:
                    self._record_health(session, h, owner_user_id=owner_user_id)
                for article in articles:
                    self._upsert_article(session, article, owner_user_id=owner_user_id)
                for event in events:
                    self._upsert_event(session, event, owner_user_id=owner_user_id)
                self._record_run(session, run_payload, owner_user_id=owner_user_id)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError(
                    "persist_failed",
                    f"collection persistence failed — no partial commit: {exc}",
                ) from exc

    def list_articles(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]:
        self.require_ready()
        with self._session() as session:
            q = select(NewsArticleRow).order_by(NewsArticleRow.ingested_at_ms.desc()).offset(offset).limit(limit)
            if owner_user_id is not None:
                q = q.where(NewsArticleRow.owner_user_id == owner_user_id)
            rows = session.scalars(q).all()
            return [self._article_dict(r) for r in rows]

    def list_events(self, *, limit: int, offset: int, owner_user_id: UUID | None) -> list[dict[str, Any]]:
        self.require_ready()
        with self._session() as session:
            q = select(NewsEventRow).order_by(NewsEventRow.available_at_ms.desc()).offset(offset).limit(limit)
            if owner_user_id is not None:
                q = q.where(NewsEventRow.owner_user_id == owner_user_id)
            rows = session.scalars(q).all()
            return [self._event_dict(session, r) for r in rows]

    def get_event(self, event_id: str, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        self.require_ready()
        with self._session() as session:
            row = session.get(NewsEventRow, event_id)
            if row is None:
                return None
            if owner_user_id is not None and row.owner_user_id not in (None, owner_user_id):
                return None
            return self._event_dict(session, row)

    def list_events_for_symbol(
        self, symbol: str, *, limit: int, owner_user_id: UUID | None
    ) -> list[dict[str, Any]]:
        self.require_ready()
        sym = symbol.upper()
        with self._session() as session:
            q = (
                select(NewsEventRow)
                .join(NewsEventAssetRow, NewsEventAssetRow.event_id == NewsEventRow.event_id)
                .where(NewsEventAssetRow.symbol == sym)
                .order_by(NewsEventRow.available_at_ms.desc())
                .limit(limit)
            )
            if owner_user_id is not None:
                q = q.where(NewsEventRow.owner_user_id == owner_user_id)
            rows = session.scalars(q).all()
            return [self._event_dict(session, r) for r in rows]

    def latest_ingestion(self, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        self.require_ready()
        with self._session() as session:
            q = select(NewsIngestionRunRow).order_by(NewsIngestionRunRow.finished_ms.desc()).limit(1)
            if owner_user_id is not None:
                q = q.where(NewsIngestionRunRow.owner_user_id == owner_user_id)
            row = session.scalars(q).first()
            if row is None:
                return None
            return {
                "run_id": row.run_id,
                "started_ms": row.started_ms,
                "finished_ms": row.finished_ms,
                "article_count": row.article_count,
                "event_count": row.event_count,
                "rejected": row.rejected,
                "duplicates_dropped": row.duplicates_dropped,
                "errors": list(row.errors_json or []),
                "provider_ids": list(row.provider_ids_json or []),
                "schema_version": row.schema_version,
                "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
            }

    def list_provider_health(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.require_ready()
        with self._session() as session:
            q = (
                select(NewsProviderHealthRow)
                .order_by(NewsProviderHealthRow.checked_ms.desc())
                .limit(limit)
            )
            rows = session.scalars(q).all()
            return [
                {
                    "provider_id": r.provider_id,
                    "ok": r.ok,
                    "checked_ms": r.checked_ms,
                    "error": r.error,
                }
                for r in rows
            ]

    # --- internal writers ---

    def _upsert_source(
        self,
        session: Session,
        *,
        provider_id: str,
        name: str,
        kind: str,
        meta: dict[str, Any],
    ) -> None:
        now = int(time.time() * 1000)
        stmt = pg_insert(NewsSourceRow).values(
            provider_id=provider_id,
            name=name,
            kind=kind,
            meta_json=meta or {},
            updated_at_ms=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["provider_id"],
            set_={
                "name": name,
                "kind": kind,
                "meta_json": meta or {},
                "updated_at_ms": now,
            },
        )
        session.execute(stmt)

    def _upsert_article(
        self,
        session: Session,
        article: ValidatedArticle,
        *,
        owner_user_id: UUID | None,
    ) -> None:
        # Prefer provider natural key so re-ingestion stays idempotent even when
        # content_hash drifts (e.g. published_at_ms shifts between collection runs).
        existing = session.scalars(
            select(NewsArticleRow).where(
                NewsArticleRow.provider_id == article.provider_id,
                NewsArticleRow.external_id == article.external_id,
            )
        ).first()
        if existing is None:
            existing = session.get(NewsArticleRow, article.content_hash)

        if existing is not None:
            existing.title = article.title
            existing.url = article.url
            existing.source_name = article.source_name
            existing.published_at_ms = article.published_at_ms
            existing.summary = article.summary
            existing.body_excerpt = article.body_excerpt
            existing.language = article.language
            existing.provider_latency_ms = article.provider_latency_ms
            existing.is_delayed_feed = article.is_delayed_feed
            existing.asset_hints_json = list(article.asset_hints)
            existing.ingested_at_ms = article.ingested_at_ms
            if owner_user_id is not None:
                existing.owner_user_id = owner_user_id
            return

        session.add(
            NewsArticleRow(
                content_hash=article.content_hash,
                provider_id=article.provider_id,
                external_id=article.external_id,
                title=article.title,
                url=article.url,
                source_name=article.source_name,
                published_at_ms=article.published_at_ms,
                first_observed_at_ms=article.first_observed_at_ms,
                ingested_at_ms=article.ingested_at_ms,
                summary=article.summary,
                body_excerpt=article.body_excerpt,
                language=article.language,
                provider_latency_ms=article.provider_latency_ms,
                is_delayed_feed=article.is_delayed_feed,
                asset_hints_json=list(article.asset_hints),
                owner_user_id=owner_user_id,
            )
        )

    def _upsert_event(
        self,
        session: Session,
        event: ClassifiedEvent,
        *,
        owner_user_id: UUID | None,
    ) -> None:
        values = {
            "event_id": event.event_id,
            "category": event.category.value,
            "severity": event.severity.value,
            "sentiment": event.sentiment.value,
            "verification": event.verification.value,
            "headline": event.headline,
            "summary": event.summary,
            "published_at_ms": event.published_at_ms,
            "first_observed_at_ms": event.first_observed_at_ms,
            "available_at_ms": event.available_at_ms,
            "classification_at_ms": event.classification_at_ms,
            "reason_codes_json": list(event.reason_codes),
            "warnings_json": list(event.warnings),
            "article_hashes_json": list(event.article_content_hashes),
            "evidence_quality": event.evidence_quality,
            "owner_user_id": owner_user_id,
        }
        stmt = pg_insert(NewsEventRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["event_id"],
            set_={
                "severity": event.severity.value,
                "sentiment": event.sentiment.value,
                "verification": event.verification.value,
                "headline": event.headline,
                "summary": event.summary,
                "available_at_ms": event.available_at_ms,
                "classification_at_ms": event.classification_at_ms,
                "reason_codes_json": list(event.reason_codes),
                "warnings_json": list(event.warnings),
                "article_hashes_json": list(event.article_content_hashes),
            },
        )
        session.execute(stmt)
        # Replace asset links
        session.execute(
            delete(NewsEventAssetRow).where(NewsEventAssetRow.event_id == event.event_id)
        )
        for sym in event.assets:
            session.add(
                NewsEventAssetRow(
                    event_id=event.event_id,
                    symbol=sym.upper(),
                    owner_user_id=owner_user_id,
                )
            )
        session.add(
            NewsClassificationRow(
                event_id=event.event_id,
                classifier_version=event.evidence_quality,
                payload_json={
                    "category": event.category.value,
                    "severity": event.severity.value,
                    "sentiment": event.sentiment.value,
                    "verification": event.verification.value,
                    "reason_codes": list(event.reason_codes),
                },
                created_at_ms=event.classification_at_ms,
                owner_user_id=owner_user_id,
            )
        )

    def _record_run(
        self,
        session: Session,
        payload: dict[str, Any],
        *,
        owner_user_id: UUID | None,
    ) -> None:
        stmt = pg_insert(NewsIngestionRunRow).values(
            run_id=str(payload["run_id"]),
            started_ms=int(payload["started_ms"]),
            finished_ms=int(payload["finished_ms"]),
            article_count=int(payload.get("article_count") or 0),
            event_count=int(payload.get("event_count") or 0),
            rejected=int(payload.get("rejected") or 0),
            duplicates_dropped=int(payload.get("duplicates_dropped") or 0),
            errors_json=list(payload.get("errors") or []),
            provider_ids_json=list(payload.get("provider_ids") or []),
            schema_version=str(payload.get("schema_version") or ""),
            owner_user_id=owner_user_id,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["run_id"])
        session.execute(stmt)

    def _record_health(
        self,
        session: Session,
        payload: dict[str, Any],
        *,
        owner_user_id: UUID | None,
    ) -> None:
        session.add(
            NewsProviderHealthRow(
                provider_id=str(payload["provider_id"]),
                ok=bool(payload.get("ok")),
                checked_ms=int(payload.get("checked_ms") or int(time.time() * 1000)),
                error=payload.get("error"),
                owner_user_id=owner_user_id,
            )
        )

    def _article_dict(self, row: NewsArticleRow) -> dict[str, Any]:
        return {
            "content_hash": row.content_hash,
            "provider_id": row.provider_id,
            "external_id": row.external_id,
            "title": row.title,
            "url": row.url,
            "source_name": row.source_name,
            "published_at_ms": row.published_at_ms,
            "first_observed_at_ms": row.first_observed_at_ms,
            "ingested_at_ms": row.ingested_at_ms,
            "summary": row.summary,
            "body_excerpt": row.body_excerpt,
            "language": row.language,
            "provider_latency_ms": row.provider_latency_ms,
            "is_delayed_feed": row.is_delayed_feed,
            "asset_hints": list(row.asset_hints_json or []),
            "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
        }

    def _event_dict(self, session: Session, row: NewsEventRow) -> dict[str, Any]:
        assets = session.scalars(
            select(NewsEventAssetRow.symbol).where(NewsEventAssetRow.event_id == row.event_id)
        ).all()
        return {
            "event_id": row.event_id,
            "category": row.category,
            "severity": row.severity,
            "sentiment": row.sentiment,
            "verification": row.verification,
            "headline": row.headline,
            "summary": row.summary,
            "assets": list(assets),
            "article_content_hashes": list(row.article_hashes_json or []),
            "published_at_ms": row.published_at_ms,
            "first_observed_at_ms": row.first_observed_at_ms,
            "available_at_ms": row.available_at_ms,
            "classification_at_ms": row.classification_at_ms,
            "reason_codes": list(row.reason_codes_json or []),
            "warnings": list(row.warnings_json or []),
            "evidence_quality": row.evidence_quality,
            "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
        }
