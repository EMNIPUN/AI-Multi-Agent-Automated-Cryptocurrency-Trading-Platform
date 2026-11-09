"""Market Data Agent — validates public candles into an immutable snapshot."""

from __future__ import annotations

from agent.candle_time import candle_close_ms, default_staleness_ms
from agent.confirmed_candles import CandleFilterReject, filter_confirmed_candles
from agent.market_data import Candle
from agent.multi_agent.types import AgentContribution, MarketCategoryKind, MarketSnapshot

AGENT_ID = "market_data"
AGENT_VERSION = "4A.1"


def build_market_snapshot(
    *,
    symbol: str,
    category: str,
    interval: str,
    candles: list[Candle],
    now_ms: int,
    data_path: str = "public_fixture",
    min_bars: int = 50,
    max_staleness_ms: int | None = None,
    news_context=None,
) -> tuple[MarketSnapshot, AgentContribution]:
    snap, contrib = _build_market_snapshot(
        symbol=symbol,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=now_ms,
        data_path=data_path,
        min_bars=min_bars,
        max_staleness_ms=max_staleness_ms,
    )
    from agent.multi_agent.news_advisory import with_news_observation

    return snap, with_news_observation(contrib, news_context, enabled=news_context is not None)


def _build_market_snapshot(
    *,
    symbol: str,
    category: str,
    interval: str,
    candles: list[Candle],
    now_ms: int,
    data_path: str = "public_fixture",
    min_bars: int = 50,
    max_staleness_ms: int | None = None,
) -> tuple[MarketSnapshot, AgentContribution]:
    cat = category.lower().strip()
    if cat not in {MarketCategoryKind.SPOT.value, MarketCategoryKind.LINEAR.value}:
        snap = MarketSnapshot(
            symbol=symbol.upper(),
            category=MarketCategoryKind.LINEAR,
            interval=interval,
            candles=(),
            closes=(),
            volumes=(),
            newest_close_ms=0,
            as_of_ms=now_ms,
            data_fresh=False,
            data_path=data_path,
            reason_codes=("INVALID_CATEGORY",),
            valid=False,
        )
        contrib = AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias="INVALID",
            confidence=0.0,
            reason_codes=("INVALID_CATEGORY",),
            explanation=f"Category '{category}' is not spot/linear",
            indicators={},
        )
        return snap, contrib

    try:
        filtered = filter_confirmed_candles(
            candles,
            interval,
            now_ms=now_ms,
            min_bars=1,
            max_staleness_ms=max_staleness_ms,
        )
    except (TypeError, ValueError, OverflowError):
        filtered = CandleFilterReject(reason="malformed candle values")
    if isinstance(filtered, CandleFilterReject):
        snap = MarketSnapshot(
            symbol=symbol.upper(),
            category=MarketCategoryKind(cat),
            interval=interval,
            candles=(),
            closes=(),
            volumes=(),
            newest_close_ms=0,
            as_of_ms=now_ms,
            data_fresh=False,
            data_path=data_path,
            reason_codes=("CANDLE_FILTER_REJECT", filtered.reason),
            valid=False,
        )
        contrib = AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias="INVALID",
            confidence=0.0,
            reason_codes=("CANDLE_FILTER_REJECT",),
            explanation=filtered.reason,
            indicators={},
        )
        return snap, contrib

    bars = filtered.candles
    reasons: list[str] = []
    gap_count = sum(
        current.start != candle_close_ms(previous.start, filtered.interval)
        for previous, current in zip(bars, bars[1:])
    )
    if gap_count:
        reasons.append("CANDLE_SEQUENCE_GAP")
    if any(min(c.open, c.high, c.low, c.close) <= 0 for c in bars):
        reasons.append("NON_POSITIVE_PRICE")
    if len(bars) < min_bars:
        reasons.append("INSUFFICIENT_BARS")

    stale_limit = max_staleness_ms
    if stale_limit is None:
        try:
            stale_limit = default_staleness_ms(interval) * 3
        except Exception:  # noqa: BLE001
            stale_limit = 60 * 60_000
    age = now_ms - filtered.newest_close_ms
    fresh = age <= stale_limit
    if not fresh:
        reasons.append("STALE_DATA")

    valid = len(bars) >= min_bars and fresh and len(reasons) == 0
    if not fresh and "STALE_DATA" in reasons and len(bars) >= min_bars:
        # Still produce a snapshot for audit, but mark invalid for decisions.
        valid = False

    snap = MarketSnapshot(
        symbol=symbol.upper(),
        category=MarketCategoryKind(cat),
        interval=filtered.interval,
        candles=tuple(bars),
        closes=tuple(c.close for c in bars),
        volumes=tuple(c.volume for c in bars),
        newest_close_ms=filtered.newest_close_ms,
        as_of_ms=now_ms,
        data_fresh=fresh,
        data_path=data_path,
        reason_codes=tuple(reasons) if reasons else ("MARKET_OK",),
        valid=valid,
    )
    conf = 1.0 if valid else 0.0
    contrib = AgentContribution(
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        bias="OK" if valid else "DEGRADED",
        confidence=conf,
        reason_codes=snap.reason_codes,
        explanation=(
            f"{len(bars)} confirmed {cat} bars; "
            f"age_ms={age}; path={data_path}"
        ),
        indicators={
            "bar_count": len(bars),
            "newest_close_ms": filtered.newest_close_ms,
            "age_ms": age,
            "skipped_forming": filtered.skipped_forming,
            "category": cat,
            "gap_count": gap_count,
        },
    )
    return snap, contrib
