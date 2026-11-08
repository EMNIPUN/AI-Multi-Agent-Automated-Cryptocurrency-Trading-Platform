"""Advisory news observations. Never changes BUY/SELL/HOLD, size, or risk verdicts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from agent.multi_agent.types import AgentContribution, RiskAssessment
from agent.news.schemas import NewsContext

ADVISORY_LABEL = "News Advisory Only — Trading Decisions Unchanged"


def disabled_advisory_record() -> dict[str, Any]:
    return {
        "enabled": False,
        "consumed": False,
        "news_changed_decision": False,
        "label": ADVISORY_LABEL,
        "storage_availability": "not_consulted",
        "freshness": "not_applicable",
        "context_status": "DISABLED",
        "source_event_ids": [],
        "warnings": [],
        "technical_news_conflict": None,
        "llm_recommendation": None,
        "diagnostic": "NEWS_AGENT_ADVISORY_ENABLED is false",
    }


def observation_from_context(ctx: NewsContext | None, *, error: str | None = None) -> dict[str, Any]:
    if ctx is None:
        return {
            "enabled": True,
            "consumed": False,
            "news_changed_decision": False,
            "label": ADVISORY_LABEL,
            "storage_availability": "unavailable",
            "freshness": "unavailable",
            "context_status": "ERROR",
            "source_event_ids": [],
            "warnings": [error or "news_context_missing"],
            "technical_news_conflict": None,
            "llm_recommendation": None,
            "diagnostic": error or "news_context_missing",
        }
    body = ctx.to_dict()
    return {
        "enabled": True,
        "consumed": True,
        "news_changed_decision": False,
        "label": ADVISORY_LABEL,
        "symbol": body["symbol"],
        "storage_availability": body.get("storage_availability"),
        "freshness": body.get("freshness"),
        "context_status": body.get("context_status"),
        "context_hash": body.get("context_hash"),
        "schema_version": body.get("schema_version"),
        "source_event_ids": list(body.get("source_event_ids") or []),
        "warnings": list(body.get("warnings") or []),
        "events": [
            {
                "event_id": event.get("event_id"),
                "category": event.get("category"),
                "severity": event.get("severity"),
                "sentiment": event.get("sentiment"),
                "verification": event.get("verification"),
                "available_at": event.get("available_at"),
            }
            for event in (body.get("events") or [])[:10]
        ],
        "technical_news_conflict": None,
        "llm_recommendation": None,
        "diagnostic": error,
        "sentiment_is_not_a_trade_signal": True,
    }


def with_news_observation(
    contrib: AgentContribution,
    ctx: NewsContext | None,
    *,
    enabled: bool,
) -> AgentContribution:
    if not enabled:
        return contrib
    indicators = dict(contrib.indicators)
    indicators["news_observation"] = observation_from_context(ctx)
    return replace(contrib, indicators=indicators)


def with_risk_observation(
    risk: RiskAssessment,
    ctx: NewsContext | None,
    *,
    enabled: bool,
) -> RiskAssessment:
    if not enabled:
        return risk
    indicators = dict(risk.indicators)
    indicators["news_observation"] = observation_from_context(ctx)
    return replace(risk, indicators=indicators)


def conflict_note(technical_action: str, ctx: NewsContext | None) -> str | None:
    if ctx is None or not ctx.events:
        return None
    sentiments = {event.sentiment for event in ctx.events}
    if technical_action == "BUY" and "NEGATIVE" in sentiments:
        return "technical_buy_with_negative_news_sentiment"
    if technical_action == "SELL" and "POSITIVE" in sentiments:
        return "technical_sell_with_positive_news_sentiment"
    return None
