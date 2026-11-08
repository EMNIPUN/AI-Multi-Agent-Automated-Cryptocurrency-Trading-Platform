"""Optional NewsData.io adapter — requires NEWSDATA_API_KEY; often delayed on free plans."""

from __future__ import annotations

import time
from typing import Any

import httpx

from agent.news.schemas import RawArticle

NEWSDATA_ENDPOINT = "https://newsdata.io/api/1/news"


class NewsDataProvider:
    provider_id = "newsdata_io"
    # Free/shared plans are frequently delayed vs wire — never claim real-time.
    is_delayed_feed = True

    def __init__(
        self,
        api_key: str,
        *,
        query: str = "bitcoin OR ethereum OR solana OR crypto",
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("NEWSDATA_API_KEY required")
        self._api_key = api_key.strip()
        self._query = query
        self._timeout = timeout
        self._client = client

    def fetch(self, *, now_ms: int) -> list[RawArticle]:
        owns = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            t0 = time.monotonic()
            res = client.get(
                NEWSDATA_ENDPOINT,
                params={
                    "apikey": self._api_key,
                    "q": self._query,
                    "language": "en",
                },
            )
            res.raise_for_status()
            latency = int((time.monotonic() - t0) * 1000)
            payload = res.json()
            if not isinstance(payload, dict):
                return []
            results = payload.get("results") or []
            out: list[RawArticle] = []
            for row in results:
                if not isinstance(row, dict):
                    continue
                art = self._map_row(row, now_ms=now_ms, latency_ms=latency)
                if art:
                    out.append(art)
            return out
        finally:
            if owns:
                client.close()

    def _map_row(self, row: dict[str, Any], *, now_ms: int, latency_ms: int) -> RawArticle | None:
        title = str(row.get("title") or "").strip()
        link = str(row.get("link") or row.get("url") or "").strip()
        if not title or not link:
            return None
        published_ms = None
        pub = row.get("pubDate") or row.get("pubDateTZ")
        if isinstance(pub, str) and pub:
            try:
                from datetime import datetime

                published_ms = int(
                    datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp() * 1000
                )
            except ValueError:
                published_ms = None
        return RawArticle(
            provider_id=self.provider_id,
            external_id=str(row.get("article_id") or link),
            title=title,
            url=link,
            source_name=str(row.get("source_id") or row.get("source_name") or "newsdata"),
            published_at_ms=published_ms,
            observed_at_ms=now_ms,
            summary=str(row.get("description") or "")[:2000],
            body_excerpt=str(row.get("content") or row.get("description") or "")[:4000],
            language=str(row.get("language") or "en"),
            provider_latency_ms=latency_ms,
            is_delayed_feed=True,
            raw={"provider": "newsdata_io"},
        )
