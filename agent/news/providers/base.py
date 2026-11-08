"""Provider protocol for news ingestion."""

from __future__ import annotations

from typing import Protocol

from agent.news.schemas import RawArticle


class NewsProvider(Protocol):
    provider_id: str
    is_delayed_feed: bool

    def fetch(self, *, now_ms: int) -> list[RawArticle]: ...
