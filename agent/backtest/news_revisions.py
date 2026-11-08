"""Append-only news revisions for point-in-time replay (Prompt 69E).

Latest-row upserts in ``app.news_events`` are not historical knowledge.
This module never invents a past classification from the current row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NewsRevision:
    event_id: str
    revision_id: str
    revision_number: int
    classification_version: str
    severity: str
    sentiment: str
    verification: str
    symbols: tuple[str, ...]
    source_evidence: tuple[str, ...]
    published_at_ms: int | None
    first_observed_at_ms: int | None
    first_available_at_ms: int | None
    revision_available_at_ms: int | None
    content_hash: str
    recorded_at_ms: int | None
    delayed_provider: bool = False

    def complete(self) -> bool:
        return (
            _ms(self.first_available_at_ms) is not None
            and _ms(self.revision_available_at_ms) is not None
            and _ms(self.recorded_at_ms) is not None
            and bool(self.event_id)
            and self.revision_number >= 1
        )


@dataclass(frozen=True)
class HistoricalNewsContext:
    symbol: str
    as_of_ms: int
    events: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    provenance_status: str
    historical_news_backtest_valid: bool
    future_excluded: int
    backfill_excluded: int
    incomplete_revisions: int
    total_visible: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of_ms": self.as_of_ms,
            "events": list(self.events),
            "warnings": list(self.warnings),
            "provenance_status": self.provenance_status,
            "historical_news_backtest_valid": self.historical_news_backtest_valid,
            "future_excluded": self.future_excluded,
            "backfill_excluded": self.backfill_excluded,
            "incomplete_revisions": self.incomplete_revisions,
            "total_visible": self.total_visible,
            "revision_history_available": self.provenance_status == "complete",
            "reconstructed_from_latest_row": False,
        }


def _ms(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > 10_000_000_000_000:
        return None
    return value


def refuse_latest_row_as_history(symbol: str, as_of_ms: int) -> HistoricalNewsContext:
    """Current ``news_events`` rows are not a point-in-time archive."""
    return HistoricalNewsContext(
        symbol=symbol.strip().upper() or "UNKNOWN",
        as_of_ms=as_of_ms if _ms(as_of_ms) is not None else 0,
        events=(),
        warnings=(
            "latest_upsert_is_not_historical_provenance",
            "historical_news_backtest_not_valid",
        ),
        provenance_status="incomplete",
        historical_news_backtest_valid=False,
        future_excluded=0,
        backfill_excluded=0,
        incomplete_revisions=0,
        total_visible=0,
    )


def build_historical_news_context(
    symbol: str,
    as_of_time: int,
    revisions: tuple[NewsRevision, ...] | list[NewsRevision],
    *,
    limit: int = 20,
    offset: int = 0,
    archive_complete: bool = False,
) -> HistoricalNewsContext:
    """Select the revision that was actually archived at or before ``as_of_time``."""
    sym = (symbol or "").strip().upper()
    clock = _ms(as_of_time)
    if clock is None or not sym:
        return HistoricalNewsContext(
            symbol=sym or "UNKNOWN",
            as_of_ms=0,
            events=(),
            warnings=("invalid_timestamp", "historical_news_backtest_not_valid"),
            provenance_status="incomplete",
            historical_news_backtest_valid=False,
            future_excluded=0,
            backfill_excluded=0,
            incomplete_revisions=0,
            total_visible=0,
        )
    warnings: list[str] = []
    future_excluded = 0
    backfill_excluded = 0
    incomplete = 0
    visible: list[NewsRevision] = []
    for rev in revisions:
        if sym not in {item.strip().upper() for item in rev.symbols}:
            continue
        if not rev.complete():
            incomplete += 1
            continue
        published = _ms(rev.published_at_ms) if rev.published_at_ms is not None else None
        if rev.published_at_ms is not None and published is None:
            incomplete += 1
            continue
        assert rev.first_available_at_ms is not None
        assert rev.revision_available_at_ms is not None
        assert rev.recorded_at_ms is not None
        known = (
            rev.first_available_at_ms <= clock
            and rev.revision_available_at_ms <= clock
            and rev.recorded_at_ms <= clock
            and (published is None or published <= clock)
        )
        if not known:
            future_excluded += 1
            if published is not None and published <= clock and rev.recorded_at_ms > clock:
                backfill_excluded += 1
            continue
        if published is None:
            warnings.append("missing_publication_time")
        if rev.delayed_provider:
            warnings.append("delayed_provider_feed")
        visible.append(rev)
    chosen: dict[str, NewsRevision] = {}
    for rev in visible:
        current = chosen.get(rev.event_id)
        if current is None or (rev.revision_number, rev.revision_id) > (
            current.revision_number,
            current.revision_id,
        ):
            chosen[rev.event_id] = rev
    ordered = sorted(
        chosen.values(),
        key=lambda rev: (int(rev.revision_available_at_ms or 0), rev.event_id),
    )
    page = ordered[max(0, offset) : max(0, offset) + max(1, min(limit, 100))]
    if incomplete:
        warnings.append("incomplete_revision_history")
    if backfill_excluded:
        warnings.append("backfilled_news_not_yet_available")
    if not revisions:
        warnings.append("no_revision_archive")
        warnings.append("latest_upsert_is_not_historical_provenance")
    provenance = "complete" if archive_complete and incomplete == 0 else "incomplete"
    if provenance != "complete":
        warnings.append("historical_news_backtest_not_valid")
    events = tuple(
        {
            "event_id": rev.event_id,
            "revision_id": rev.revision_id,
            "revision_number": rev.revision_number,
            "classification_version": rev.classification_version,
            "severity": rev.severity,
            "sentiment": rev.sentiment,
            "verification": rev.verification,
            "published_at_ms": rev.published_at_ms,
            "first_observed_at_ms": rev.first_observed_at_ms,
            "first_available_at_ms": rev.first_available_at_ms,
            "revision_available_at_ms": rev.revision_available_at_ms,
            "content_hash": rev.content_hash,
            "recorded_at_ms": rev.recorded_at_ms,
            "delayed_provider": rev.delayed_provider,
            "source_evidence": list(rev.source_evidence),
        }
        for rev in page
    )
    return HistoricalNewsContext(
        symbol=sym,
        as_of_ms=clock,
        events=events,
        warnings=tuple(dict.fromkeys(warnings)),
        provenance_status=provenance,
        historical_news_backtest_valid=provenance == "complete",
        future_excluded=future_excluded,
        backfill_excluded=backfill_excluded,
        incomplete_revisions=incomplete,
        total_visible=len(ordered),
    )
