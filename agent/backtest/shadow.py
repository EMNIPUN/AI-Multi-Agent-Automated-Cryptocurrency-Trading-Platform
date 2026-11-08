"""Shadow labels on an existing 68A result. Does not rerun or change decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from agent.backtest.models import BacktestResult, BacktestStatus
from agent.backtest.news_revisions import NewsRevision, build_historical_news_context
from agent.backtest.report import compute_result_hash

HISTORICAL_SIM_LABEL = "Historical Simulation — Not Live Trading"
ADVISORY_UNCHANGED_LABEL = "Advisory Only — Trading Decisions Unchanged"
RESEARCH_HYPOTHESES = (
    "avoid_new_entries_during_verified_critical_events",
    "require_confirmation_during_high_uncertainty",
    "reduce_exposure_under_market_wide_stress",
)


@dataclass(frozen=True)
class RecordedLlmAdvice:
    """A recommendation that was stored at ``completed_at_ms``. Not a live model call."""

    evaluation_id: str
    symbol: str
    completed_at_ms: int
    suggested_action: str
    abstain: bool
    validation_result: str
    evidence_event_ids: tuple[str, ...]
    model: str
    prompt_version: str
    retrospective: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0


def research_policy_status() -> dict[str, Any]:
    return {
        "activated": False,
        "changes_coordinator": False,
        "changes_risk_agent": False,
        "changes_position_size": False,
        "hypotheses": list(RESEARCH_HYPOTHESES),
        "label": "research hypothesis only",
    }


def _llm_for(symbol: str, as_of_ms: int, records: tuple[RecordedLlmAdvice, ...]) -> dict[str, Any]:
    historical = [
        row
        for row in records
        if row.symbol.upper() == symbol
        and not row.retrospective
        and row.completed_at_ms <= as_of_ms
        and row.validation_result == "accepted"
    ]
    retrospective = [
        row
        for row in records
        if row.symbol.upper() == symbol and row.retrospective and row.completed_at_ms <= as_of_ms
    ]
    future = sum(1 for row in records if row.symbol.upper() == symbol and row.completed_at_ms > as_of_ms)
    failed = sum(
        1
        for row in records
        if row.symbol.upper() == symbol
        and row.completed_at_ms <= as_of_ms
        and row.validation_result != "accepted"
    )
    historical.sort(key=lambda row: (row.completed_at_ms, row.evaluation_id))
    chosen = historical[-1] if historical else None
    return {
        "historical_signal": None
        if chosen is None
        else {
            "evaluation_id": chosen.evaluation_id,
            "suggested_action": chosen.suggested_action,
            "abstain": chosen.abstain,
            "model": chosen.model,
            "prompt_version": chosen.prompt_version,
            "evidence_event_ids": list(chosen.evidence_event_ids),
            "label": "recorded_before_as_of",
        },
        "retrospective_experiment_count": len(retrospective),
        "retrospective_is_not_a_historical_signal": True,
        "future_records_excluded": future,
        "validation_failures": failed,
        "openai_called": False,
    }


def _conflict(action: str, events: list[dict[str, Any]]) -> bool:
    sentiments = {str(event.get("sentiment")) for event in events}
    if action == "BUY" and "NEGATIVE" in sentiments:
        return True
    if action == "SELL" and "POSITIVE" in sentiments:
        return True
    return False


def annotate_shadow(
    result: BacktestResult,
    *,
    mode: str,
    revisions: tuple[NewsRevision, ...] = (),
    llm_records: tuple[RecordedLlmAdvice, ...] = (),
    archive_complete: bool = False,
) -> BacktestResult:
    """Attach advisory observations. The technical result itself is not recomputed."""
    if mode not in {"technical_baseline", "news_advisory_shadow", "llm_advisory_shadow"}:
        raise ValueError("unknown evaluation mode")
    if result.status is not BacktestStatus.COMPLETED:
        return result
    observations: list[dict[str, Any]] = []
    lookahead = 0
    for decision in result.decisions:
        context = build_historical_news_context(
            result.dataset.symbol,
            decision.now_ms,
            revisions,
            archive_complete=archive_complete,
        )
        for event in context.events:
            if int(event["revision_available_at_ms"]) > decision.now_ms:
                lookahead += 1
            if int(event["recorded_at_ms"]) > decision.now_ms:
                lookahead += 1
        llm = _llm_for(result.dataset.symbol, decision.now_ms, llm_records) if mode == "llm_advisory_shadow" else {
            "historical_signal": None,
            "retrospective_experiment_count": 0,
            "retrospective_is_not_a_historical_signal": True,
            "future_records_excluded": 0,
            "validation_failures": 0,
            "openai_called": False,
        }
        signal = llm["historical_signal"]
        if signal and signal["abstain"]:
            agreement = "abstain"
        elif signal and signal["suggested_action"] == decision.action:
            agreement = "agree"
        elif signal:
            agreement = "disagree"
        else:
            agreement = "not_applicable"
        observations.append(
            {
                "candle_start_ms": decision.candle_start_ms,
                "now_ms": decision.now_ms,
                "technical_action": decision.action,
                "risk_verdict": decision.risk_verdict,
                "position_notional": decision.position_notional,
                "news_event_ids": [event["event_id"] for event in context.events],
                "news_severity": [event["severity"] for event in context.events],
                "news_sentiment": [event["sentiment"] for event in context.events],
                "freshness_warnings": list(context.warnings),
                "provenance_status": context.provenance_status,
                "conflict": _conflict(decision.action, list(context.events)),
                "llm_agreement": agreement,
                "llm_changed_decision": False,
                "news_changed_decision": False,
            }
        )
    valid_flags = []
    if mode == "technical_baseline":
        provenance = "not_applicable"
        historical_valid = False
    else:
        sample = build_historical_news_context(
            result.dataset.symbol,
            result.dataset.last_start_ms,
            revisions,
            archive_complete=archive_complete,
        )
        provenance = sample.provenance_status
        historical_valid = sample.historical_news_backtest_valid
        valid_flags.append(historical_valid)
    covered = sum(1 for row in observations if row["news_event_ids"])
    conflicts = sum(1 for row in observations if row["conflict"])
    agreements = sum(1 for row in observations if row["llm_agreement"] == "agree")
    disagreements = sum(1 for row in observations if row["llm_agreement"] == "disagree")
    abstentions = sum(1 for row in observations if row["llm_agreement"] == "abstain")
    evals = max(1, len(observations))
    analytics = result.analytics or {}
    shadow = {
        "mode": mode,
        "label": HISTORICAL_SIM_LABEL,
        "advisory_label": None if mode == "technical_baseline" else ADVISORY_UNCHANGED_LABEL,
        "decisions_unchanged": True,
        "news_changed_decision": False,
        "llm_changed_decision": False,
        "performance_improvement_claimed": False,
        "profitability_claimed": False,
        "agreement_is_not_profitability": True,
        "openai_called": False,
        "historical_news_backtest_valid": bool(valid_flags and all(valid_flags)),
        "provenance_status": provenance,
        "baseline_result_hash": result.result_hash,
        "dataset_hash": result.dataset.content_hash,
        "simulator": "spot-like long-only; not a leveraged futures backtest",
        "research_policies": research_policy_status(),
        "lookahead_violations": lookahead,
        "metrics": {
            "technical": {
                "net_realized_pnl": analytics.get("net_realized_pnl"),
                "max_drawdown_marked": analytics.get("max_drawdown_marked"),
                "win_rate_pct": analytics.get("win_rate_pct"),
                "profit_factor": analytics.get("profit_factor"),
                "expectancy": analytics.get("expectancy"),
                "total_fees": analytics.get("total_fees"),
                "closed_trades": analytics.get("closed_trades"),
                "note": "Copied from the technical simulation. Advisory modes do not produce a separate return.",
            },
            "news": {
                "coverage_rate": round(covered / evals, 4) if observations else None,
                "revision_coverage": provenance,
                "conflict_rate": round(conflicts / evals, 4) if observations else None,
                "evaluations": len(observations),
            },
            "llm": {
                "agreement_rate": round(agreements / evals, 4) if mode == "llm_advisory_shadow" else None,
                "disagreement_rate": round(disagreements / evals, 4) if mode == "llm_advisory_shadow" else None,
                "abstention_rate": round(abstentions / evals, 4) if mode == "llm_advisory_shadow" else None,
                "openai_called": False,
                "note": "Rates use previously recorded advice only. They are not returns.",
            },
        },
        "observations": observations[:50],
        "observations_truncated": len(observations) > 50,
    }
    extras = dict(result.extras)
    extras["shadow_69e"] = shadow
    drafted = replace(result, extras=extras, result_hash="")
    return replace(drafted, result_hash=compute_result_hash(drafted))
