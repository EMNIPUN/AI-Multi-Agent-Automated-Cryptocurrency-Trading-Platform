"""News collection orchestration — validate, dedupe, classify (Prompt 69A)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

from agent.news.config import NewsConfig
from agent.news.deduplicator import dedupe_articles
from agent.news.event_classifier import classify_article
from agent.news.providers.base import NewsProvider
from agent.news.relevance import infer_assets
from agent.news.schemas import ClassifiedEvent, ValidatedArticle
from agent.news.validator import NewsValidationError, validate_article


@dataclass
class CollectionResult:
    run_id: str
    started_ms: int
    finished_ms: int
    articles: list[ValidatedArticle] = field(default_factory=list)
    events: list[ClassifiedEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    provider_ids: list[str] = field(default_factory=list)
    rejected: int = 0
    duplicates_dropped: int = 0
    alerts_created: int = 0
    alerts_suppressed: int = 0
    telegram_confirmed: int = 0


def collect_news(
    providers: Sequence[NewsProvider],
    *,
    config: NewsConfig | None = None,
    now_ms: int | None = None,
    run_id: str | None = None,
) -> CollectionResult:
    cfg = config or NewsConfig.from_env()
    clock = now_ms if now_ms is not None else int(time.time() * 1000)
    rid = run_id or f"nir_{clock}"
    result = CollectionResult(run_id=rid, started_ms=clock, finished_ms=clock)

    if not cfg.collection_enabled:
        result.errors.append("collection_disabled")
        result.finished_ms = int(time.time() * 1000)
        return result

    raw_validated: list[ValidatedArticle] = []
    for provider in providers:
        result.provider_ids.append(provider.provider_id)
        try:
            raw_list = provider.fetch(now_ms=clock)
        except Exception as exc:  # noqa: BLE001 — isolate provider failures
            result.errors.append(f"{provider.provider_id}:fetch:{exc}")
            continue
        for raw in raw_list[: cfg.max_articles_per_run]:
            try:
                hints = infer_assets(
                    f"{raw.title} {raw.summary}",
                    monitored=cfg.monitored_symbols,
                )
                validated = validate_article(raw, ingested_at_ms=clock, asset_hints=hints)
                raw_validated.append(validated)
            except NewsValidationError as exc:
                result.rejected += 1
                result.errors.append(f"reject:{exc.code}")

    before = len(raw_validated)
    articles = dedupe_articles(raw_validated)[: cfg.max_articles_per_run]
    result.duplicates_dropped = max(0, before - len(articles))
    result.articles = articles

    # Corroboration: count articles sharing normalized overlapping assets+category keywords later;
    # for 69A use per-article classify with corroborating_count=1 unless same title family exists.
    title_counts: dict[str, int] = {}
    for a in articles:
        key = a.title.strip().lower()[:80]
        title_counts[key] = title_counts.get(key, 0) + 1

    events: list[ClassifiedEvent] = []
    for a in articles:
        corr = title_counts.get(a.title.strip().lower()[:80], 1)
        ev = classify_article(
            a,
            monitored=cfg.monitored_symbols,
            now_ms=clock,
            corroborating_count=corr,
        )
        if ev is not None:
            events.append(ev)
    result.events = events
    result.finished_ms = int(time.time() * 1000)
    return result
