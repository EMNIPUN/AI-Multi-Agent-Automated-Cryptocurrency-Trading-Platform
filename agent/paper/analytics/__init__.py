"""Deterministic paper performance analytics — read-only, journal-sourced."""

from agent.paper.analytics.models import (
    ClosedTradeMetrics,
    MetricAvailability,
    SessionAnalytics,
)
from agent.paper.analytics.service import (
    AnalyticsError,
    compute_session_analytics,
    list_equity_points,
    list_trade_metrics,
)

__all__ = [
    "AnalyticsError",
    "ClosedTradeMetrics",
    "MetricAvailability",
    "SessionAnalytics",
    "compute_session_analytics",
    "list_equity_points",
    "list_trade_metrics",
]
