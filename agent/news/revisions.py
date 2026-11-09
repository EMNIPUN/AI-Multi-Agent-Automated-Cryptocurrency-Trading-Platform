"""Decide whether a classified event needs a new append-only revision.

Does not invent revisions for events that were stored before the archive existed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from agent.news.schemas import ClassifiedEvent


@dataclass(frozen=True)
class RevisionDraft:
    revision_id: str
    event_id: str
    revision_number: int
    classification_version: str
    severity: str
    sentiment: str
    verification: str
    symbols: tuple[str, ...]
    source_evidence: tuple[str, ...]
    published_at_ms: int | None
    first_observed_at_ms: int
    first_available_at_ms: int
    revision_available_at_ms: int
    content_hash: str
    recorded_at_ms: int
    delayed_provider: bool


def material_key(event: ClassifiedEvent) -> str:
    hashes = ",".join(event.article_content_hashes)
    return "|".join(
        (
            event.severity.value,
            event.sentiment.value,
            event.verification.value,
            event.evidence_quality,
            hashes,
        )
    )


def plan_revision(
    event: ClassifiedEvent,
    *,
    prior_number: int,
    prior_material: str | None,
    recorded_at_ms: int,
    delayed_provider: bool = False,
) -> RevisionDraft | None:
    """Return a new revision, or None when the latest archive row already matches."""
    current = material_key(event)
    if prior_material == current:
        return None
    number = prior_number + 1
    if number < 1:
        number = 1
    observed = event.first_observed_at_ms
    available = event.available_at_ms
    classified = event.classification_at_ms
    revision_available = max(available, classified, recorded_at_ms)
    digest = hashlib.sha256(f"{event.event_id}:{number}:{current}".encode("utf-8")).hexdigest()[:16]
    evidence = tuple(event.article_content_hashes)
    content_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
    return RevisionDraft(
        revision_id=f"nrev_{digest}",
        event_id=event.event_id,
        revision_number=number,
        classification_version=event.evidence_quality,
        severity=event.severity.value,
        sentiment=event.sentiment.value,
        verification=event.verification.value,
        symbols=tuple(symbol.upper() for symbol in event.assets),
        source_evidence=evidence,
        published_at_ms=event.published_at_ms,
        first_observed_at_ms=observed,
        first_available_at_ms=available,
        revision_available_at_ms=revision_available,
        content_hash=content_hash,
        recorded_at_ms=recorded_at_ms,
        delayed_provider=delayed_provider,
    )
