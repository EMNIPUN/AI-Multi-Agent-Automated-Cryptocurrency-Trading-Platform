"""Deterministic event classification — severity ≠ sentiment (Prompt 69A)."""

from __future__ import annotations

import hashlib
import time

from agent.news.relevance import infer_assets, is_crypto_relevant
from agent.news.schemas import (
    ClassifiedEvent,
    EventCategory,
    Sentiment,
    Severity,
    ValidatedArticle,
    VerificationStatus,
)

_CATEGORY_RULES: list[tuple[EventCategory, tuple[str, ...]]] = [
    (EventCategory.SECURITY_INCIDENT, ("hack", "breach", "stolen", "exploit", "security incident")),
    (EventCategory.PROTOCOL_EXPLOIT, ("protocol exploit", "smart contract exploit", "drained")),
    (EventCategory.NETWORK_OUTAGE, ("network outage", "chain halt", "mainnet down", "consensus failure")),
    (EventCategory.STABLECOIN, ("depeg", "stablecoin", "usdt", "usdc", "peg loss")),
    (EventCategory.EXCHANGE_OPS, ("withdrawal suspend", "withdrawals halted", "deposit suspend", "delist")),
    (EventCategory.DELISTING, ("delisting", "delist")),
    (EventCategory.REGULATORY, ("sec ", "cftc", "regulatory", "enforcement", "lawsuit", "ban ")),
    (EventCategory.MARKET_INFRA, ("oracle failure", "clearing halt", "trading halt")),
]

_CRITICAL_PHRASES = (
    "exchange hack",
    "hot wallet breach",
    "withdrawals suspended",
    "withdrawals halted",
    "major depeg",
    "stablecoin depeg",
    "chain halt",
    "network outage",
    "protocol exploit",
)

_HIGH_PHRASES = (
    "security breach",
    "funds stolen",
    "enforcement action",
    "delisting",
    "trading halt",
)

_NEGATIVE = ("hack", "breach", "stolen", "exploit", "ban", "lawsuit", "crash", "halt", "suspend", "depeg")
_POSITIVE = ("approval", "etf approved", "partnership", "launch", "record high", "surge")


def _blob(article: ValidatedArticle) -> str:
    return f"{article.title} {article.summary} {article.body_excerpt}".lower()


def classify_category(text: str) -> EventCategory:
    for cat, phrases in _CATEGORY_RULES:
        if any(p in text for p in phrases):
            return cat
    if is_crypto_relevant(text):
        return EventCategory.GENERAL
    return EventCategory.UNKNOWN


def classify_sentiment(text: str) -> Sentiment:
    neg = sum(1 for p in _NEGATIVE if p in text)
    pos = sum(1 for p in _POSITIVE if p in text)
    if neg and pos:
        return Sentiment.MIXED
    if neg >= 2:
        return Sentiment.NEGATIVE
    if pos >= 2:
        return Sentiment.POSITIVE
    if neg:
        return Sentiment.NEGATIVE
    if pos:
        return Sentiment.POSITIVE
    return Sentiment.NEUTRAL


def classify_severity(text: str, category: EventCategory) -> Severity:
    # Negative tone alone is NOT critical.
    if any(p in text for p in _CRITICAL_PHRASES):
        return Severity.CRITICAL
    if any(p in text for p in _HIGH_PHRASES):
        return Severity.HIGH
    if category in {
        EventCategory.SECURITY_INCIDENT,
        EventCategory.PROTOCOL_EXPLOIT,
        EventCategory.NETWORK_OUTAGE,
        EventCategory.STABLECOIN,
    }:
        return Severity.MEDIUM
    if category in {EventCategory.REGULATORY, EventCategory.EXCHANGE_OPS, EventCategory.DELISTING}:
        return Severity.MEDIUM
    if category is EventCategory.GENERAL:
        return Severity.LOW
    if category is EventCategory.UNKNOWN:
        return Severity.UNKNOWN
    return Severity.INFORMATIONAL


def classify_verification(
    article: ValidatedArticle,
    *,
    corroborating_count: int = 1,
) -> VerificationStatus:
    name = (article.source_name or "").lower()
    official_markers = ("sec.gov", "cftc.gov", "bybit", "binance", "coinbase", "federal reserve")
    if any(m in name or m in article.url.lower() for m in official_markers):
        return VerificationStatus.OFFICIAL_SOURCE
    if corroborating_count >= 2:
        return VerificationStatus.CORROBORATED
    if article.provider_id:
        return VerificationStatus.SINGLE_SOURCE
    return VerificationStatus.UNVERIFIED


def make_event_id(article: ValidatedArticle, category: EventCategory) -> str:
    seed = f"{article.content_hash}|{category.value}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    return f"nev_{digest}"


def classify_article(
    article: ValidatedArticle,
    *,
    monitored: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    now_ms: int | None = None,
    corroborating_count: int = 1,
) -> ClassifiedEvent | None:
    text = _blob(article)
    if not is_crypto_relevant(text) and not article.asset_hints:
        return None
    assets = article.asset_hints or infer_assets(text, monitored=monitored)
    category = classify_category(text)
    severity = classify_severity(text, category)
    sentiment = classify_sentiment(text)
    verification = classify_verification(article, corroborating_count=corroborating_count)
    clock = now_ms if now_ms is not None else int(time.time() * 1000)
    available = max(article.first_observed_at_ms, article.ingested_at_ms)
    warnings: list[str] = []
    if article.is_delayed_feed:
        warnings.append("delayed_provider_feed")
    if article.provider_latency_ms is not None and article.provider_latency_ms > 3_600_000:
        warnings.append("provider_latency_over_1h")
    if verification is VerificationStatus.UNVERIFIED:
        warnings.append("unverified_source")
    reasons = (
        f"category:{category.value}",
        f"severity:{severity.value}",
        f"sentiment:{sentiment.value}",
        f"verification:{verification.value}",
    )
    return ClassifiedEvent(
        event_id=make_event_id(article, category),
        category=category,
        severity=severity,
        sentiment=sentiment,
        verification=verification,
        headline=article.title,
        summary=article.summary or article.title,
        assets=assets,
        article_content_hashes=(article.content_hash,),
        published_at_ms=article.published_at_ms,
        first_observed_at_ms=article.first_observed_at_ms,
        available_at_ms=available,
        classification_at_ms=clock,
        reason_codes=reasons,
        warnings=tuple(warnings),
    )
