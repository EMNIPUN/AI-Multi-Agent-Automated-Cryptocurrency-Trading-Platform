"""Equity / balance series construction from persisted observations."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent.paper.analytics.models import EquityPoint, SeriesType
from agent.paper.config import d


def realized_balance_series(
    snapshots: list[dict[str, Any]],
) -> tuple[list[EquityPoint], list[str]]:
    """
    Cash identity series: available + reserved from each snapshot.

    This is NOT marked equity when open positions have price moves.
    """
    warnings: list[str] = []
    points: list[EquityPoint] = []
    seen_ms: set[int] = set()
    for row in snapshots:
        ms = int(row["as_of_ms"])
        if ms in seen_ms:
            warnings.append(f"duplicate_snapshot_timestamp:{ms}")
            continue
        seen_ms.add(ms)
        avail = d(row["available_balance"])
        reserved = d(row["reserved_capital"])
        points.append(
            EquityPoint(
                as_of_ms=ms,
                value=avail + reserved,
                valuation_status=str(row.get("valuation_status") or "unknown"),
                series_type=SeriesType.REALIZED_BALANCE,
            )
        )
    if len(points) < 3:
        warnings.append("sparse_realized_balance_observations")
    return points, warnings


def marked_equity_series(
    snapshots: list[dict[str, Any]],
) -> tuple[list[EquityPoint], list[str]]:
    """
    Mark-to-market equity from snapshots with valid marked_equity.

    Requires valuation_status in {ok, flat}. Never substitutes entry for mark.
    Does not interpolate missing points.
    """
    warnings: list[str] = []
    points: list[EquityPoint] = []
    seen_ms: set[int] = set()
    skipped = 0
    for row in snapshots:
        status = str(row.get("valuation_status") or "").lower()
        marked = row.get("marked_equity")
        if status not in {"ok", "flat"} or marked is None:
            skipped += 1
            continue
        ms = int(row["as_of_ms"])
        if ms in seen_ms:
            warnings.append(f"duplicate_marked_snapshot_timestamp:{ms}")
            continue
        seen_ms.add(ms)
        try:
            value = d(marked)
        except Exception:  # noqa: BLE001
            warnings.append(f"invalid_marked_equity_at:{ms}")
            continue
        if value < 0:
            warnings.append(f"negative_marked_equity_at:{ms}")
            continue
        points.append(
            EquityPoint(
                as_of_ms=ms,
                value=value,
                valuation_status=status,
                series_type=SeriesType.MARKED_EQUITY,
            )
        )
    if skipped:
        warnings.append(f"skipped_invalid_or_unavailable_marks:{skipped}")
    if len(points) < 3:
        warnings.append("sparse_marked_equity_observations")
    return points, warnings


def reconstruct_realized_balance_from_trades(
    *,
    initial_balance: Decimal,
    trade_nets_by_exit_ms: list[tuple[int, Decimal]],
) -> list[EquityPoint]:
    """
    Fallback realized-only step curve when snapshots are missing:
    balance after each closed trade = initial + cumulative net PnL.
    """
    points = [
        EquityPoint(
            as_of_ms=0,
            value=d(initial_balance),
            valuation_status="reconstructed",
            series_type=SeriesType.REALIZED_BALANCE,
        )
    ]
    cum = d(initial_balance)
    for ms, net in sorted(trade_nets_by_exit_ms, key=lambda x: x[0]):
        cum = cum + d(net)
        points.append(
            EquityPoint(
                as_of_ms=int(ms),
                value=cum,
                valuation_status="reconstructed",
                series_type=SeriesType.REALIZED_BALANCE,
            )
        )
    return points
