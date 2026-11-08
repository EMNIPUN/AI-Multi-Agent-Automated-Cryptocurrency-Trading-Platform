"""Postgres alert repository (Prompt 69B). Fail closed when 0008 is not applied."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from apps.api.app.news.pg_repository import NewsStorageError
from apps.api.app.persistence.news_models import (
    NewsAlertDeliveryRow,
    NewsAlertPreferenceRow,
    NewsAlertRow,
)


def _owner(value: UUID | None) -> str | None:
    return str(value) if value else None


class PostgresAlertRepository:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name == "sqlite":
            raise NewsStorageError("sqlite_forbidden", "News alerts must not use SQLite.")
        if engine.dialect.name not in {"postgresql", "postgres"}:
            raise NewsStorageError("unsupported_dialect", f"PostgreSQL required, got {engine.dialect.name}")
        self._engine = engine
        self._Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def storage_kind(self) -> str:
        return "supabase_postgres"

    def alerts_ready(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM app.news_alerts LIMIT 1"))
            return True
        except SQLAlchemyError:
            return False

    def list_alerts(
        self,
        *,
        limit: int,
        offset: int,
        owner_user_id: UUID | None,
        severity: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        self._require()
        with self._Session() as session:
            q = select(NewsAlertRow).order_by(NewsAlertRow.created_at_ms.desc())
            if owner_user_id is not None:
                q = q.where(NewsAlertRow.owner_user_id == owner_user_id)
            if severity:
                q = q.where(NewsAlertRow.severity == severity)
            if status:
                q = q.where(NewsAlertRow.status == status)
            rows = session.scalars(q).all()
            out = [self._alert_dict(r) for r in rows]
            if symbol:
                sym = symbol.upper()
                out = [r for r in out if sym in [str(s).upper() for s in r["symbols"]]]
            return out[offset : offset + limit]

    def get_alert(self, alert_id: str, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        self._require()
        with self._Session() as session:
            row = session.get(NewsAlertRow, alert_id)
            if row is None:
                return None
            if owner_user_id is not None and row.owner_user_id not in (None, owner_user_id):
                return None
            return self._alert_dict(row)

    def unread_count(self, *, owner_user_id: UUID | None) -> int:
        rows = self.list_alerts(limit=500, offset=0, owner_user_id=owner_user_id, status="OPEN")
        return len(rows)

    def upsert_alerts(self, rows: list[dict[str, Any]]) -> None:
        self._require()
        with self._Session() as session:
            try:
                for row in rows:
                    stmt = pg_insert(NewsAlertRow).values(**self._alert_values(row))
                    stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"])
                    session.execute(stmt)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"alert persist failed: {exc}") from exc

    def acknowledge(self, alert_id: str, *, now_ms: int, owner_user_id: UUID | None) -> dict[str, Any] | None:
        self._require()
        with self._Session() as session:
            try:
                row = session.get(NewsAlertRow, alert_id)
                if row is None:
                    return None
                if owner_user_id is not None and row.owner_user_id not in (None, owner_user_id):
                    return None
                if row.status != "ACKNOWLEDGED":
                    row.status = "ACKNOWLEDGED"
                    row.acknowledged_at_ms = now_ms
                    row.updated_at_ms = now_ms
                session.commit()
                return self._alert_dict(row)
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"acknowledge failed: {exc}") from exc

    def get_preferences(self, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        self._require()
        key = "operator_default" if owner_user_id is None else str(owner_user_id)
        with self._Session() as session:
            row = session.get(NewsAlertPreferenceRow, key)
            if row is None:
                return None
            return self._pref_dict(row)

    def save_preferences(self, prefs: dict[str, Any], *, owner_user_id: UUID | None) -> dict[str, Any]:
        self._require()
        key = "operator_default" if owner_user_id is None else str(owner_user_id)
        now = int(prefs.get("updated_at_ms") or time.time() * 1000)
        with self._Session() as session:
            try:
                stmt = pg_insert(NewsAlertPreferenceRow).values(
                    preference_id=key,
                    owner_user_id=owner_user_id,
                    min_severity=str(prefs.get("min_severity") or "HIGH"),
                    symbols_json=list(prefs.get("symbols") or []),
                    cooldown_ms=int(prefs["cooldown_ms"]),
                    ttl_ms=int(prefs["ttl_ms"]),
                    in_app_enabled=bool(prefs.get("in_app_enabled", True)),
                    telegram_enabled=bool(prefs.get("telegram_enabled", False)),
                    updated_at_ms=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["preference_id"],
                    set_={
                        "min_severity": str(prefs.get("min_severity") or "HIGH"),
                        "symbols_json": list(prefs.get("symbols") or []),
                        "cooldown_ms": int(prefs["cooldown_ms"]),
                        "ttl_ms": int(prefs["ttl_ms"]),
                        "in_app_enabled": bool(prefs.get("in_app_enabled", True)),
                        "telegram_enabled": bool(prefs.get("telegram_enabled", False)),
                        "updated_at_ms": now,
                    },
                )
                session.execute(stmt)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"preference persist failed: {exc}") from exc
        stored = self.get_preferences(owner_user_id=owner_user_id)
        return stored or {}

    def record_delivery(self, row: dict[str, Any]) -> dict[str, Any]:
        self._require()
        with self._Session() as session:
            try:
                existing = session.scalars(
                    select(NewsAlertDeliveryRow).where(
                        NewsAlertDeliveryRow.idempotency_key == row["idempotency_key"]
                    )
                ).first()
                if existing and existing.status == "confirmed":
                    return self._delivery_dict(existing)
                if existing is None:
                    session.add(
                        NewsAlertDeliveryRow(
                            delivery_id=str(row["delivery_id"]),
                            alert_id=str(row["alert_id"]),
                            owner_user_id=row.get("owner_user_id"),
                            channel=str(row["channel"]),
                            status=str(row["status"]),
                            attempt_count=int(row.get("attempt_count") or 0),
                            provider_message_id=row.get("provider_message_id"),
                            confirmed_at_ms=row.get("confirmed_at_ms"),
                            last_error=row.get("last_error"),
                            idempotency_key=str(row["idempotency_key"]),
                            created_at_ms=int(row["created_at_ms"]),
                            updated_at_ms=int(row["updated_at_ms"]),
                        )
                    )
                else:
                    existing.status = str(row["status"])
                    existing.attempt_count = int(row.get("attempt_count") or 0)
                    existing.provider_message_id = row.get("provider_message_id")
                    existing.confirmed_at_ms = row.get("confirmed_at_ms")
                    existing.last_error = row.get("last_error")
                    existing.updated_at_ms = int(row["updated_at_ms"])
                session.commit()
                saved = session.scalars(
                    select(NewsAlertDeliveryRow).where(
                        NewsAlertDeliveryRow.idempotency_key == row["idempotency_key"]
                    )
                ).first()
                return self._delivery_dict(saved) if saved else dict(row)
            except SQLAlchemyError as exc:
                session.rollback()
                raise NewsStorageError("persist_failed", f"delivery persist failed: {exc}") from exc

    def get_delivery(self, idempotency_key: str) -> dict[str, Any] | None:
        self._require()
        with self._Session() as session:
            row = session.scalars(
                select(NewsAlertDeliveryRow).where(NewsAlertDeliveryRow.idempotency_key == idempotency_key)
            ).first()
            return self._delivery_dict(row) if row else None

    def try_acquire_collection_lease(self, owner_id: str, *, now_ms: int, ttl_ms: int) -> bool:
        self._require()
        exp = now_ms + ttl_ms
        sql = text(
            """
            INSERT INTO app.news_collection_lease
                (lease_name, owner_id, acquired_at_ms, expires_at_ms)
            VALUES ('news_collect', :owner, :now, :exp)
            ON CONFLICT (lease_name) DO UPDATE
            SET owner_id = EXCLUDED.owner_id,
                acquired_at_ms = EXCLUDED.acquired_at_ms,
                expires_at_ms = EXCLUDED.expires_at_ms
            WHERE app.news_collection_lease.expires_at_ms < :now
               OR app.news_collection_lease.owner_id = EXCLUDED.owner_id
            RETURNING owner_id
            """
        )
        with self._engine.begin() as conn:
            row = conn.execute(sql, {"owner": owner_id, "now": now_ms, "exp": exp}).first()
            return row is not None

    def release_collection_lease(self, owner_id: str, *, now_ms: int) -> None:
        if not self.alerts_ready():
            return
        sql = text(
            """
            UPDATE app.news_collection_lease
            SET expires_at_ms = :now
            WHERE lease_name = 'news_collect' AND owner_id = :owner
            """
        )
        with self._engine.begin() as conn:
            conn.execute(sql, {"owner": owner_id, "now": now_ms})

    def _require(self) -> None:
        if not self.alerts_ready():
            raise NewsStorageError(
                "alerts_schema_unavailable",
                "app.news_alerts is missing. Apply Alembic 20261108_0008 on the development target after approval.",
            )

    def _alert_values(self, row: dict[str, Any]) -> dict[str, Any]:
        owner = row.get("owner_user_id")
        if isinstance(owner, str):
            owner = UUID(owner)
        return {
            "alert_id": row["alert_id"],
            "event_id": row["event_id"],
            "owner_user_id": owner,
            "severity": row["severity"],
            "category": row["category"],
            "status": row.get("status") or "OPEN",
            "headline": row["headline"],
            "summary": row.get("summary") or "",
            "explanation": row.get("explanation") or "",
            "symbols_json": list(row.get("symbols") or []),
            "verification": row["verification"],
            "source_url": row.get("source_url"),
            "article_hashes_json": list(row.get("article_hashes") or []),
            "published_at_ms": row.get("published_at_ms"),
            "first_observed_at_ms": int(row["first_observed_at_ms"]),
            "detected_at_ms": int(row["detected_at_ms"]),
            "available_at_ms": int(row["available_at_ms"]),
            "created_at_ms": int(row["created_at_ms"]),
            "updated_at_ms": int(row["updated_at_ms"]),
            "acknowledged_at_ms": row.get("acknowledged_at_ms"),
            "expires_at_ms": int(row["expires_at_ms"]),
            "material_fingerprint": row["material_fingerprint"],
            "idempotency_key": row["idempotency_key"],
            "warnings_json": list(row.get("warnings") or []),
            "evidence_json": dict(row.get("evidence") or {}),
            "freshness": row.get("freshness") or "unknown",
            "agent_context_json": dict(row.get("agent_context") or {}),
        }

    def _alert_dict(self, row: NewsAlertRow) -> dict[str, Any]:
        return {
            "alert_id": row.alert_id,
            "event_id": row.event_id,
            "owner_user_id": _owner(row.owner_user_id),
            "severity": row.severity,
            "category": row.category,
            "status": row.status,
            "headline": row.headline,
            "summary": row.summary,
            "explanation": row.explanation,
            "symbols": list(row.symbols_json or []),
            "verification": row.verification,
            "source_url": row.source_url,
            "article_hashes": list(row.article_hashes_json or []),
            "published_at_ms": row.published_at_ms,
            "first_observed_at_ms": row.first_observed_at_ms,
            "detected_at_ms": row.detected_at_ms,
            "available_at_ms": row.available_at_ms,
            "created_at_ms": row.created_at_ms,
            "updated_at_ms": row.updated_at_ms,
            "acknowledged_at_ms": row.acknowledged_at_ms,
            "expires_at_ms": row.expires_at_ms,
            "material_fingerprint": row.material_fingerprint,
            "idempotency_key": row.idempotency_key,
            "warnings": list(row.warnings_json or []),
            "evidence": dict(row.evidence_json or {}),
            "freshness": row.freshness,
            "agent_context": dict(row.agent_context_json or {}),
        }

    def _pref_dict(self, row: NewsAlertPreferenceRow) -> dict[str, Any]:
        return {
            "preference_id": row.preference_id,
            "owner_user_id": _owner(row.owner_user_id),
            "min_severity": row.min_severity,
            "symbols": list(row.symbols_json or []),
            "cooldown_ms": row.cooldown_ms,
            "ttl_ms": row.ttl_ms,
            "in_app_enabled": row.in_app_enabled,
            "telegram_enabled": row.telegram_enabled,
            "updated_at_ms": row.updated_at_ms,
        }

    def _delivery_dict(self, row: NewsAlertDeliveryRow) -> dict[str, Any]:
        return {
            "delivery_id": row.delivery_id,
            "alert_id": row.alert_id,
            "channel": row.channel,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "provider_message_id": row.provider_message_id,
            "confirmed_at_ms": row.confirmed_at_ms,
            "last_error": row.last_error,
            "idempotency_key": row.idempotency_key,
            "confirmed": row.status == "confirmed",
        }
