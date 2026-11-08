"""Peak-to-trough drawdown on a labeled equity/balance series."""

from __future__ import annotations

from decimal import Decimal

from agent.paper.accounting import q
from agent.paper.analytics.models import (
    DrawdownResult,
    EquityPoint,
    MetricAvailability,
    OptionalDecimal,
    SeriesType,
)
from agent.paper.config import d


def max_drawdown(points: list[EquityPoint], *, sparse_threshold: int = 3) -> DrawdownResult:
    series_type = (
        points[0].series_type if points else SeriesType.REALIZED_BALANCE
    )
    if series_type is SeriesType.MARKED_EQUITY:
        label = "Maximum observed marked-equity drawdown"
    else:
        label = "Maximum observed realized-balance drawdown"

    notes: list[str] = []
    sparse = len(points) < sparse_threshold
    if sparse:
        notes.append(
            "Sparse observations — intraperiod drawdown may have been larger"
        )
    if not points:
        return DrawdownResult(
            max_drawdown_pct=OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_observations"
            ),
            max_drawdown_amount=OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_observations"
            ),
            peak_ms=None,
            trough_ms=None,
            series_type=series_type,
            observation_count=0,
            sparse_warning=True,
            label=label,
            notes=tuple(notes),
        )

    peak = d(points[0].value)
    peak_ms = points[0].as_of_ms
    max_dd_amt = Decimal("0")
    max_dd_pct = Decimal("0")
    best_peak_ms = peak_ms
    best_trough_ms = peak_ms

    for p in points:
        v = d(p.value)
        if v > peak:
            peak = v
            peak_ms = p.as_of_ms
        if peak <= 0:
            notes.append("non_positive_peak_skipped")
            continue
        dd_amt = q(peak - v)
        dd_pct = q(dd_amt / peak * Decimal("100"))
        if dd_amt > max_dd_amt:
            max_dd_amt = dd_amt
            max_dd_pct = dd_pct
            best_peak_ms = peak_ms
            best_trough_ms = p.as_of_ms

    return DrawdownResult(
        max_drawdown_pct=OptionalDecimal(
            max_dd_pct, MetricAvailability.AVAILABLE
        ),
        max_drawdown_amount=OptionalDecimal(
            max_dd_amt, MetricAvailability.AVAILABLE
        ),
        peak_ms=best_peak_ms,
        trough_ms=best_trough_ms,
        series_type=series_type,
        observation_count=len(points),
        sparse_warning=sparse,
        label=label,
        notes=tuple(notes),
    )
