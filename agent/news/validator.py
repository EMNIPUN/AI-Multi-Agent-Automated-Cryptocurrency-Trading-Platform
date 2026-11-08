"""Article validation — treat all external text as untrusted."""

from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urlparse

from agent.news.schemas import RawArticle, ValidatedArticle

_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "execute tool",
    "place trade",
    "disclose secrets",
    "api key",
)


class NewsValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise NewsValidationError("missing_url", "article url required")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise NewsValidationError("invalid_url", "url must be http(s)")
    if not parsed.netloc:
        raise NewsValidationError("invalid_url", "url host required")
    return text


def content_hash(*, title: str, url: str, published_at_ms: int | None) -> str:
    raw = f"{title.strip().lower()}|{url.strip().lower()}|{published_at_ms or 0}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sanitize_text(text: str, *, max_len: int = 4000) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned[:max_len]


def detect_prompt_injection(text: str) -> tuple[str, ...]:
    low = (text or "").lower()
    hits = [m for m in _INJECTION_MARKERS if m in low]
    return tuple(hits)


def validate_article(
    raw: RawArticle,
    *,
    ingested_at_ms: int | None = None,
    asset_hints: tuple[str, ...] = (),
) -> ValidatedArticle:
    title = sanitize_text(raw.title, max_len=500)
    if len(title) < 8:
        raise NewsValidationError("title_too_short", "title too short")
    url = _normalize_url(raw.url)
    summary = sanitize_text(raw.summary, max_len=2000)
    excerpt = sanitize_text(raw.body_excerpt, max_len=4000)
    inj = detect_prompt_injection(f"{title} {summary} {excerpt}")
    # Strip nothing silently — record via empty body if injection-heavy; keep title for audit.
    if len(inj) >= 2:
        excerpt = ""
        summary = sanitize_text(summary[:200] + " [untrusted_content_truncated]")

    now = ingested_at_ms if ingested_at_ms is not None else int(time.time() * 1000)
    published = raw.published_at_ms
    if published is not None and published > now + 60_000:
        raise NewsValidationError("future_publish", "published_at is in the future")
    if published is not None and published <= 0:
        published = None

    return ValidatedArticle(
        content_hash=content_hash(title=title, url=url, published_at_ms=published),
        provider_id=raw.provider_id.strip(),
        external_id=(raw.external_id or "").strip() or url,
        title=title,
        url=url,
        source_name=sanitize_text(raw.source_name, max_len=120) or "unknown",
        published_at_ms=published,
        first_observed_at_ms=int(raw.observed_at_ms),
        ingested_at_ms=now,
        summary=summary,
        body_excerpt=excerpt,
        language=(raw.language or "en")[:16],
        provider_latency_ms=raw.provider_latency_ms,
        is_delayed_feed=bool(raw.is_delayed_feed),
        asset_hints=asset_hints,
    )
