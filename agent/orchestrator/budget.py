"""Orchestrator OpenAI spend reservation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agent.orchestrator.usage_ledger import UsageLedger


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class BudgetCaps:
    daily_usd: float = 1.0
    monthly_usd: float = 5.0
    total_usd: float = 5.0
    reserve_usd: float = 0.05  # conservative per-request hold


def caps_from_env() -> BudgetCaps:
    return BudgetCaps(
        daily_usd=max(0.0, _env_float("CRYPTONOVA_ORCHESTRATOR_DAILY_BUDGET_USD", 1.0)),
        monthly_usd=max(0.0, _env_float("CRYPTONOVA_ORCHESTRATOR_MONTHLY_BUDGET_USD", 5.0)),
        total_usd=max(0.0, _env_float("CRYPTONOVA_ORCHESTRATOR_TOTAL_BUDGET_USD", 5.0)),
        reserve_usd=max(0.01, _env_float("CRYPTONOVA_ORCHESTRATOR_RESERVE_USD", 0.05)),
    )


@dataclass
class BudgetReservation:
    ok: bool
    key: str
    reason: str

    @property
    def blocked(self) -> bool:
        return not self.ok


def reserve_spend(
    ledger: UsageLedger,
    *,
    model: str = "",
    idempotency_key: str | None = None,
    caps: BudgetCaps | None = None,
) -> BudgetReservation:
    cfg = caps or caps_from_env()
    ok, key, reason = ledger.try_reserve(
        reserved_usd=cfg.reserve_usd,
        daily_budget_usd=cfg.daily_usd,
        monthly_budget_usd=cfg.monthly_usd,
        total_budget_usd=cfg.total_usd,
        idempotency_key=idempotency_key,
        model=model,
    )
    return BudgetReservation(ok=ok, key=key, reason=reason)


def commit_spend(
    ledger: UsageLedger,
    reservation: BudgetReservation,
    *,
    actual_usd: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model: str = "",
) -> None:
    if not reservation.key:
        return
    ledger.commit_reservation(
        reservation.key,
        actual_usd=actual_usd,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model,
    )


def release_spend(ledger: UsageLedger, reservation: BudgetReservation) -> None:
    if reservation.key:
        ledger.release_reservation(reservation.key)


def public_budget_status(ledger: UsageLedger, caps: BudgetCaps | None = None) -> dict[str, Any]:
    cfg = caps or caps_from_env()
    summary = ledger.summary()
    spent_day = float(summary.get("spent_usd_24h") or 0.0)
    spent_month = float(summary.get("spent_usd_30d") or 0.0)
    spent_total = float(summary.get("spent_usd_total") or 0.0)
    return {
        **summary,
        "daily_budget_usd": cfg.daily_usd,
        "monthly_budget_usd": cfg.monthly_usd,
        "total_budget_usd": cfg.total_usd,
        "remaining_usd_24h": max(0.0, cfg.daily_usd - spent_day),
        "remaining_usd_30d": max(0.0, cfg.monthly_usd - spent_month),
        "remaining_usd_total": max(0.0, cfg.total_usd - spent_total),
    }
