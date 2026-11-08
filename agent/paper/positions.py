"""Position helpers for paper broker (spot-like unleveraged longs)."""

from __future__ import annotations

from agent.paper.models import PaperPosition, PositionStatus


def is_open(position: PaperPosition) -> bool:
    return position.status is PositionStatus.OPEN


def is_closed(position: PaperPosition) -> bool:
    return position.status is PositionStatus.CLOSED
