"""Article deduplication by content hash and near-duplicate titles."""

from __future__ import annotations

import re

from agent.news.schemas import ValidatedArticle


def _norm_title(title: str) -> str:
    t = re.sub(r"[^a-z0-9\s]", "", (title or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def dedupe_articles(articles: list[ValidatedArticle]) -> list[ValidatedArticle]:
    """Keep first occurrence per content_hash; drop exact URL/title duplicates."""
    seen_hash: set[str] = set()
    seen_title: set[str] = set()
    out: list[ValidatedArticle] = []
    for a in articles:
        if a.content_hash in seen_hash:
            continue
        nt = _norm_title(a.title)
        if nt and nt in seen_title:
            continue
        seen_hash.add(a.content_hash)
        if nt:
            seen_title.add(nt)
        out.append(a)
    return out
