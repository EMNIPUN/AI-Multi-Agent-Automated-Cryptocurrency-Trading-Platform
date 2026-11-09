"""Append-only revision insert. Missing archive does not roll back article persistence."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agent.news.revisions import plan_revision
from agent.news.schemas import ClassifiedEvent


def append_event_revision(
    session: Session,
    event: ClassifiedEvent,
    *,
    recorded_at_ms: int,
    owner_user_id,
    delayed_provider: bool = False,
) -> str:
    nested = session.begin_nested()
    try:
        session.execute(text("SELECT 1 FROM app.news_event_revisions LIMIT 1"))
        row = session.execute(
            text(
                """
                SELECT revision_number, content_hash
                FROM app.news_event_revisions
                WHERE event_id = :event_id
                ORDER BY revision_number DESC
                LIMIT 1
                """
            ),
            {"event_id": event.event_id},
        ).mappings().first()
        prior_number = int(row["revision_number"]) if row else 0
        from agent.news.revisions import material_key

        current_hash = hashlib.sha256(material_key(event).encode("utf-8")).hexdigest()
        if row is not None and str(row["content_hash"]) == current_hash:
            nested.commit()
            return "duplicate"
        draft = plan_revision(
            event,
            prior_number=prior_number,
            prior_material=None,
            recorded_at_ms=recorded_at_ms,
            delayed_provider=delayed_provider,
        )
        if draft is None:
            nested.commit()
            return "duplicate"
        session.execute(
            text(
                """
                INSERT INTO app.news_event_revisions (
                    revision_id, event_id, revision_number, classification_version,
                    severity, sentiment, verification, symbols_json, source_evidence_json,
                    published_at_ms, first_observed_at_ms, first_available_at_ms,
                    revision_available_at_ms, content_hash, recorded_at_ms,
                    delayed_provider, owner_user_id
                ) VALUES (
                    :revision_id, :event_id, :revision_number, :classification_version,
                    :severity, :sentiment, :verification, CAST(:symbols_json AS jsonb),
                    CAST(:source_evidence_json AS jsonb), :published_at_ms, :first_observed_at_ms,
                    :first_available_at_ms, :revision_available_at_ms, :content_hash,
                    :recorded_at_ms, :delayed_provider, :owner_user_id
                )
                ON CONFLICT (event_id, revision_number) DO NOTHING
                """
            ),
            {
                "revision_id": draft.revision_id,
                "event_id": draft.event_id,
                "revision_number": draft.revision_number,
                "classification_version": draft.classification_version,
                "severity": draft.severity,
                "sentiment": draft.sentiment,
                "verification": draft.verification,
                "symbols_json": json.dumps(list(draft.symbols)),
                "source_evidence_json": json.dumps(list(draft.source_evidence)),
                "published_at_ms": draft.published_at_ms,
                "first_observed_at_ms": draft.first_observed_at_ms,
                "first_available_at_ms": draft.first_available_at_ms,
                "revision_available_at_ms": draft.revision_available_at_ms,
                "content_hash": draft.content_hash,
                "recorded_at_ms": draft.recorded_at_ms,
                "delayed_provider": draft.delayed_provider,
                "owner_user_id": owner_user_id,
            },
        )
        nested.commit()
        return "appended"
    except SQLAlchemyError:
        nested.rollback()
        return "archive_unavailable"
