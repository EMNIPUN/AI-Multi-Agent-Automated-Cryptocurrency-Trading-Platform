"""Historical OHLCV dataset loading — public/fixture only; no private APIs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from agent.backtest.models import DatasetIdentity
from agent.backtest.validation import ValidationReport, validate_candle_series
from agent.market_data import Candle


def candle_content_hash(candles: Sequence[Candle]) -> str:
    parts: list[str] = []
    for c in candles:
        parts.append(
            f"{int(c.start)}|{c.open}|{c.high}|{c.low}|{c.close}|{c.volume}"
        )
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def candles_to_rows(candles: Sequence[Candle]) -> list[dict[str, Any]]:
    return [
        {
            "start": int(c.start),
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        }
        for c in candles
    ]


def rows_to_candles(rows: Sequence[dict[str, Any]]) -> list[Candle]:
    out: list[Candle] = []
    for row in rows:
        out.append(
            Candle(
                start=int(row["start"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0)),
            )
        )
    return out


def load_fixture_file(path: str | Path) -> tuple[list[Candle], dict[str, Any]]:
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        meta: dict[str, Any] = {"provenance": f"fixture_file:{p.as_posix()}"}
        rows = payload
    elif isinstance(payload, dict):
        meta = dict(payload.get("meta") or {})
        meta.setdefault("provenance", f"fixture_file:{p.as_posix()}")
        rows = payload.get("candles") or payload.get("ohlcv") or []
    else:
        raise ValueError("fixture must be a list or object with candles")
    return rows_to_candles(rows), meta


def save_fixture_file(
    path: str | Path,
    candles: Sequence[Candle],
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "meta": {
            **(meta or {}),
            "content_hash": candle_content_hash(candles),
            "candle_count": len(candles),
            "label": "OFFLINE / SYNTHETIC OR HISTORICAL — NOT LIVE STREAM",
        },
        "candles": candles_to_rows(candles),
    }
    p.write_text(json.dumps(body, indent=2), encoding="utf-8")


def build_dataset(
    candles: list[Candle],
    *,
    symbol: str,
    interval: str,
    market_type: str,
    provenance: str,
    source_kind: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    allow_gaps: bool = True,
) -> tuple[DatasetIdentity, ValidationReport]:
    filtered = candles
    if start_ms is not None:
        filtered = [c for c in filtered if int(c.start) >= start_ms]
    if end_ms is not None:
        filtered = [c for c in filtered if int(c.start) <= end_ms]
    report = validate_candle_series(filtered, interval=interval, allow_gaps=allow_gaps)
    identity = DatasetIdentity(
        symbol=symbol,
        interval=interval,
        market_type=market_type,
        candle_count=len(report.candles),
        first_start_ms=int(report.candles[0].start),
        last_start_ms=int(report.candles[-1].start),
        content_hash=candle_content_hash(report.candles),
        provenance=provenance,
        source_kind=source_kind,
        warnings=report.warnings,
    )
    return identity, report


def synthetic_trend_candles(
    *,
    n: int = 240,
    start_ms: int = 1_700_000_000_000,
    interval_ms: int = 15 * 60_000,
    start_price: float = 40_000.0,
    drift: float = 0.0012,
    volume: float = 12.0,
) -> list[Candle]:
    """Deterministic offline fixture builder (no network)."""
    out: list[Candle] = []
    px = float(start_price)
    for i in range(n):
        prev = px
        # Mild deterministic oscillation around drift — no RNG.
        step = drift if (i % 11) != 0 else drift * 0.15
        if (i % 23) == 0:
            step = -abs(drift) * 0.8
        px = prev * (1.0 + step)
        high = max(prev, px) * 1.0015
        low = min(prev, px) * 0.9985
        out.append(
            Candle(
                start=start_ms + i * interval_ms,
                open=prev,
                high=high,
                low=low,
                close=px,
                volume=volume * (1.0 + (i % 7) * 0.04),
            )
        )
    return out
