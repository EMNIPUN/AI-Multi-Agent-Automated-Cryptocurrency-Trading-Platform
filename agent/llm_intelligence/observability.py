"""Aggregate stored evaluations. Agreement is not a profitability claim."""

from __future__ import annotations

from agent.llm_intelligence.schemas import LlmEvaluation


def comparison_report(rows: list[LlmEvaluation]) -> dict[str, object]:
    total = len(rows)
    if total == 0:
        return {
            "evaluations": 0,
            "agreement_rate": None,
            "disagreement_rate": None,
            "abstention_rate": None,
            "error_rate": None,
            "missing_or_stale_news_rate": None,
            "average_latency_ms": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_usd": 0.0,
            "note": "No evaluations. Agreement is not evidence of profitability.",
        }
    agree = sum(1 for row in rows if row.agreement == "agree")
    disagree = sum(1 for row in rows if row.agreement == "disagree")
    abstain = sum(1 for row in rows if row.agreement == "abstain" or row.abstain)
    errors = sum(1 for row in rows if row.status not in {"accepted", "disabled"})
    stale = sum(
        1
        for row in rows
        if any("stale" in w or "missing" in w or "revision_snapshots" in w for w in row.warnings)
    )
    latency = [max(0, row.completed_at_ms - row.requested_at_ms) for row in rows]
    prompt = sum(int(row.token_usage.get("prompt_tokens") or 0) for row in rows)
    completion = sum(int(row.token_usage.get("completion_tokens") or 0) for row in rows)
    cost = sum(row.estimated_cost_usd for row in rows)
    return {
        "evaluations": total,
        "agreement_rate": round(agree / total, 4),
        "disagreement_rate": round(disagree / total, 4),
        "abstention_rate": round(abstain / total, 4),
        "error_rate": round(errors / total, 4),
        "missing_or_stale_news_rate": round(stale / total, 4),
        "average_latency_ms": round(sum(latency) / total, 2),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "estimated_cost_usd": round(cost, 6),
        "note": "Rates describe stored advisory rows only. They do not measure returns.",
    }
