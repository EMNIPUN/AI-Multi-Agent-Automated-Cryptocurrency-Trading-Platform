"""Versioned news domain types (Prompt 69A). Advisory-only; not trading instructions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"
    UNKNOWN = "UNKNOWN"


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(str, Enum):
    OFFICIAL_SOURCE = "OFFICIAL_SOURCE"
    CORROBORATED = "CORROBORATED"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class EventCategory(str, Enum):
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    NETWORK_OUTAGE = "NETWORK_OUTAGE"
    REGULATORY = "REGULATORY"
    EXCHANGE_OPS = "EXCHANGE_OPS"
    STABLECOIN = "STABLECOIN"
    PROTOCOL_EXPLOIT = "PROTOCOL_EXPLOIT"
    DELISTING = "DELISTING"
    MARKET_INFRA = "MARKET_INFRA"
    MACRO = "MACRO"
    GENERAL = "GENERAL"
    UNKNOWN = "UNKNOWN"


class ContextStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RawArticle:
    provider_id: str
    external_id: str
    title: str
    url: str
    source_name: str
    published_at_ms: int | None
    observed_at_ms: int
    summary: str = ""
    body_excerpt: str = ""
    language: str = "en"
    raw: dict[str, Any] = field(default_factory=dict)
    provider_latency_ms: int | None = None
    is_delayed_feed: bool = False


@dataclass(frozen=True)
class ValidatedArticle:
    content_hash: str
    provider_id: str
    external_id: str
    title: str
    url: str
    source_name: str
    published_at_ms: int | None
    first_observed_at_ms: int
    ingested_at_ms: int
    summary: str
    body_excerpt: str
    language: str
    provider_latency_ms: int | None
    is_delayed_feed: bool
    asset_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClassifiedEvent:
    event_id: str
    category: EventCategory
    severity: Severity
    sentiment: Sentiment
    verification: VerificationStatus
    headline: str
    summary: str
    assets: tuple[str, ...]
    article_content_hashes: tuple[str, ...]
    published_at_ms: int | None
    first_observed_at_ms: int
    available_at_ms: int
    classification_at_ms: int
    reason_codes: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_quality: str = "rule_based_v1"


@dataclass(frozen=True)
class NewsContextEvent:
    event_id: str
    category: str
    severity: str
    sentiment: str
    verification: str
    source_ids: tuple[str, ...]
    published_at: str | None
    first_observed_at: str
    available_at: str
    summary: str
    warnings: tuple[str, ...] = ()
    freshness: str = "unknown"
    delayed_provider: bool = False
    corroboration: str = "unknown"
    source_references: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NewsContext:
    """Immutable per-evaluation snapshot for later 69C wiring (advisory)."""

    symbol: str
    as_of: str
    events: tuple[NewsContextEvent, ...]
    context_status: ContextStatus
    schema_version: str
    warnings: tuple[str, ...] = ()
    evaluation_time_utc: str = ""
    context_generated_at_utc: str = ""
    source_event_ids: tuple[str, ...] = ()
    freshness: str = "unknown"
    delayed_provider: bool = False
    corroboration_status: str = "unknown"
    data_completeness: str = "empty"
    storage_availability: str = "unknown"
    context_hash: str = ""
    revision_history_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "evaluation_time_utc": self.evaluation_time_utc or self.as_of,
            "context_generated_at_utc": self.context_generated_at_utc,
            "source_event_ids": list(self.source_event_ids),
            "events": [e.to_dict() for e in self.events],
            "context_status": self.context_status.value,
            "schema_version": self.schema_version,
            "warnings": list(self.warnings),
            "freshness": self.freshness,
            "delayed_provider": self.delayed_provider,
            "corroboration_status": self.corroboration_status,
            "data_completeness": self.data_completeness,
            "storage_availability": self.storage_availability,
            "context_hash": self.context_hash,
            "revision_history_available": self.revision_history_available,
            "sentiment_is_not_a_trade_signal": True,
        }
