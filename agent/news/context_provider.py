"""Point-in-time NewsContext snapshots (Prompt 69C). Advisory only."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from agent.news.config import NEWS_CONTEXT_SCHEMA_VERSION, NewsConfig
from agent.news.repository import NewsRepository
from agent.news.schemas import ContextStatus, NewsContext, NewsContextEvent

# Current rows are upserted in place. Prior revisions are not stored.
REVISION_GAP = "revision_snapshots_unavailable"


def _iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_ms(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > 10_000_000_000_000:
        return None
    return value


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def unavailable_news_context(
    symbol: str,
    as_of_ms: int,
    *warnings: str,
    storage_availability: str = "unavailable",
    status: ContextStatus = ContextStatus.UNAVAILABLE,
) -> NewsContext:
    as_of = _iso(as_of_ms) or ""
    base_warnings = (REVISION_GAP, *warnings)
    payload = {
        "symbol": symbol.strip().upper(),
        "evaluation_time_utc": as_of,
        "source_event_ids": [],
        "warnings": list(base_warnings),
        "schema_version": NEWS_CONTEXT_SCHEMA_VERSION,
    }
    return NewsContext(
        symbol=payload["symbol"],
        as_of=as_of,
        events=(),
        context_status=status,
        schema_version=NEWS_CONTEXT_SCHEMA_VERSION,
        warnings=tuple(base_warnings),
        evaluation_time_utc=as_of,
        context_generated_at_utc=as_of,
        source_event_ids=(),
        freshness="unavailable",
        delayed_provider=False,
        corroboration_status="unknown",
        data_completeness="empty",
        storage_availability=storage_availability,
        context_hash=_hash_payload(payload),
        revision_history_available=False,
    )


def build_news_context(
    repo: NewsRepository,
    *,
    symbol: str,
    as_of_ms: int | None = None,
    as_of_time: int | None = None,
    config: NewsConfig | None = None,
    owner_user_id=None,
    stale_after_ms: int = 6 * 60 * 60 * 1000,
    generated_at_ms: int | None = None,
) -> NewsContext:
    """Events visible at ``as_of_ms`` use first-available time, not publication time alone."""
    clock = as_of_ms if as_of_ms is not None else as_of_time
    sym = (symbol or "").strip().upper()
    if _valid_ms(clock) is None or not sym:
        return unavailable_news_context(
            sym or "UNKNOWN",
            0,
            "invalid_timestamp",
            storage_availability="not_queried",
            status=ContextStatus.ERROR,
        )
    as_of = int(clock)
    cfg = config or NewsConfig()
    generated = _valid_ms(generated_at_ms) or as_of
    try:
        events_raw = list(
            repo.list_events_for_symbol(
                sym, limit=max(cfg.max_events_per_context * 5, cfg.max_events_per_context), owner_user_id=owner_user_id
            )
        )
    except Exception:  # noqa: BLE001 — news storage must not raise into callers
        return unavailable_news_context(
            sym,
            as_of,
            "news_storage_unavailable",
            storage_availability="unavailable",
            status=ContextStatus.ERROR,
        )

    selected: dict[str, dict[str, Any]] = {}
    future_excluded = 0
    for row in events_raw:
        available = int(row.get("available_at_ms") or 0)
        classified = row.get("classification_at_ms")
        if available > as_of:
            future_excluded += 1
            continue
        if classified is not None and int(classified) > as_of:
            # Latest row is a future revision. The prior snapshot is not stored.
            future_excluded += 1
            continue
        event_id = str(row.get("event_id") or "")
        if not event_id:
            continue
        current = selected.get(event_id)
        if current is None or available < int(current.get("available_at_ms") or 0):
            selected[event_id] = row

    ordered = sorted(
        selected.values(),
        key=lambda row: (int(row.get("available_at_ms") or 0), str(row.get("event_id"))),
    )
    if len(ordered) > cfg.max_events_per_context:
        ordered = ordered[-cfg.max_events_per_context :]

    extra_warnings = [REVISION_GAP]
    if future_excluded:
        extra_warnings.append("future_events_excluded")

    if not ordered:
        try:
            latest = repo.latest_ingestion(owner_user_id=owner_user_id)
        except Exception:  # noqa: BLE001
            latest = None
        extra_warnings.append("no_news_ingestion" if latest is None else "no_events_for_symbol")
        ctx = unavailable_news_context(
            sym,
            as_of,
            *extra_warnings[1:],
            storage_availability="available",
            status=ContextStatus.UNAVAILABLE,
        )
        return NewsContext(
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            events=(),
            context_status=ctx.context_status,
            schema_version=ctx.schema_version,
            warnings=tuple(dict.fromkeys((*ctx.warnings, *extra_warnings))),
            evaluation_time_utc=_iso(as_of) or "",
            context_generated_at_utc=_iso(generated) or "",
            freshness="missing",
            data_completeness="empty",
            storage_availability="available",
            context_hash=ctx.context_hash,
            revision_history_available=False,
        )

    newest_available = max(int(row.get("available_at_ms") or 0) for row in ordered)
    freshness = "fresh"
    status = ContextStatus.AVAILABLE
    if as_of - newest_available > stale_after_ms:
        status = ContextStatus.STALE
        freshness = "stale"
        extra_warnings.append("news_context_stale")
    elif any(row.get("verification") in {"UNVERIFIED", "UNKNOWN"} for row in ordered):
        status = ContextStatus.UNVERIFIED
        extra_warnings.append("contains_unverified_events")

    events: list[NewsContextEvent] = []
    delayed = False
    missing_published = 0
    corroborations: set[str] = set()
    for row in ordered:
        warnings = tuple(str(w) for w in (row.get("warnings") or ()))
        row_delayed = "delayed_provider_feed" in warnings or bool(row.get("is_delayed_feed"))
        delayed = delayed or row_delayed
        if row.get("published_at_ms") is None:
            missing_published += 1
        verification = str(row.get("verification") or "UNKNOWN")
        corroborations.add(verification)
        if row_delayed:
            freshness = "delayed" if freshness == "fresh" else freshness
        events.append(
            NewsContextEvent(
                event_id=str(row.get("event_id")),
                category=str(row.get("category") or "UNKNOWN"),
                severity=str(row.get("severity") or "UNKNOWN"),
                sentiment=str(row.get("sentiment") or "UNKNOWN"),
                verification=verification,
                source_ids=tuple(str(x) for x in (row.get("article_content_hashes") or ())),
                published_at=_iso(row.get("published_at_ms")),
                first_observed_at=_iso(int(row.get("first_observed_at_ms") or 0)) or "",
                available_at=_iso(int(row.get("available_at_ms") or 0)) or "",
                summary=str(row.get("summary") or row.get("headline") or "")[:280],
                warnings=warnings,
                freshness="delayed" if row_delayed else ("stale" if status is ContextStatus.STALE else "fresh"),
                delayed_provider=row_delayed,
                corroboration=verification,
                source_references=tuple(
                    ref
                    for ref in (str(row.get("source_url") or ""), str(row.get("headline") or ""))
                    if ref
                )[:4],
            )
        )

    if delayed:
        extra_warnings.append("delayed_provider_feed")
    if "CORROBORATED" in corroborations or "OFFICIAL_SOURCE" in corroborations:
        corroboration_status = "corroborated_or_official_present"
    elif corroborations == {"SINGLE_SOURCE"}:
        corroboration_status = "single_source"
    else:
        corroboration_status = "mixed_or_unverified"
    completeness = "complete" if missing_published == 0 else "partial_missing_publication_time"
    event_ids = tuple(event.event_id for event in events)
    hash_body = {
        "symbol": sym,
        "evaluation_time_utc": _iso(as_of),
        "source_event_ids": list(event_ids),
        "schema_version": NEWS_CONTEXT_SCHEMA_VERSION,
    }
    return NewsContext(
        symbol=sym,
        as_of=_iso(as_of) or "",
        events=tuple(events),
        context_status=status,
        schema_version=NEWS_CONTEXT_SCHEMA_VERSION,
        warnings=tuple(dict.fromkeys(extra_warnings)),
        evaluation_time_utc=_iso(as_of) or "",
        context_generated_at_utc=_iso(generated) or "",
        source_event_ids=event_ids,
        freshness=freshness,
        delayed_provider=delayed,
        corroboration_status=corroboration_status,
        data_completeness=completeness,
        storage_availability="available",
        context_hash=_hash_payload(hash_body),
        revision_history_available=False,
    )


def context_to_public_dict(ctx: NewsContext) -> dict[str, Any]:
    return ctx.to_dict()
