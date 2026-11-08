"""Prompt 68C — historical public candle loader + dataset cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.backtest.data import candle_content_hash, synthetic_trend_candles
from agent.backtest.dataset_cache import (
    DatasetCacheError,
    load_dataset_cache,
    save_dataset_cache,
)
from agent.backtest.history_provider import (
    FakeHistoryTransport,
    HistoryProviderError,
    estimate_candle_count,
    fetch_historical_candles,
    validate_history_request,
)
from agent.backtest.limits import DEFAULT_PAGE_LIMIT
from agent.market_data import Candle


def _row(start: int, px: float = 100.0) -> list:
    return [start, str(px), str(px + 1), str(px - 1), str(px + 0.5), "10"]


def test_estimate_and_validate_range() -> None:
    start = 1_700_000_000_000
    end = start + 15 * 60_000 * 99
    assert estimate_candle_count(start, end, "15") == 100
    with pytest.raises(HistoryProviderError) as exc:
        validate_history_request(
            symbol="DOGEUSDT",
            market_type="spot",
            interval="15",
            start_ms=start,
            end_ms=end,
        )
    assert exc.value.code == "unsupported_symbol"


def test_unsupported_interval_and_future_range() -> None:
    start = 1_700_000_000_000
    with pytest.raises(HistoryProviderError) as exc:
        validate_history_request(
            symbol="BTCUSDT",
            market_type="spot",
            interval="7",
            start_ms=start,
            end_ms=start + 60_000,
        )
    assert "unsupported" in exc.value.code or "interval" in exc.value.message.lower()

    with pytest.raises(HistoryProviderError) as exc2:
        validate_history_request(
            symbol="BTCUSDT",
            market_type="spot",
            interval="15",
            start_ms=start,
            end_ms=9_999_999_999_999,
        )
    assert exc2.value.code == "future_range"


def test_pagination_dedupe_and_ordering() -> None:
    interval_ms = 15 * 60_000
    base = 1_700_000_000_000
    # Two overlapping pages (newest-first within each page).
    page1_starts = [base + i * interval_ms for i in range(0, 5)]
    page2_starts = [base + i * interval_ms for i in range(4, 9)]  # overlap at 4

    pages = {
        "first": {
            "retCode": 0,
            "result": {"list": [_row(s, 100 + i) for i, s in enumerate(reversed(page1_starts))]},
        },
        "second": {
            "retCode": 0,
            "result": {
                "list": [_row(s, 100 + i) for i, s in enumerate(reversed(page2_starts))]
            },
        },
        "empty": {"retCode": 0, "result": {"list": []}},
        "instruments": {
            "retCode": 0,
            "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading"}]},
        },
    }
    state = {"n": 0}

    def handler(path: str, params: dict):
        if path.endswith("instruments-info"):
            return pages["instruments"]
        state["n"] += 1
        if state["n"] == 1:
            return pages["first"]
        if state["n"] == 2:
            return pages["second"]
        return pages["empty"]

    transport = FakeHistoryTransport(handler)
    # Force pages shorter than DEFAULT_PAGE_LIMIT so second page still fetched via cursor.
    # Our loader continues while page is full OR cursor advances; with 5 < 1000 it stops
    # after first short page. Force full-page behavior by monkeypatching via many rows.
    # Instead: return full page_limit rows on first call.
    many = [base + i * interval_ms for i in range(DEFAULT_PAGE_LIMIT)]
    overlap_tail = [base + (DEFAULT_PAGE_LIMIT - 1 + i) * interval_ms for i in range(5)]

    def handler2(path: str, params: dict):
        if path.endswith("instruments-info"):
            return pages["instruments"]
        start = int(params.get("start") or 0)
        if start <= base:
            return {
                "retCode": 0,
                "result": {"list": [_row(s) for s in reversed(many)]},
            }
        if start <= overlap_tail[0] + 1:
            return {
                "retCode": 0,
                "result": {"list": [_row(s) for s in reversed(overlap_tail)]},
            }
        return {"retCode": 0, "result": {"list": []}}

    transport = FakeHistoryTransport(handler2)
    now = base + (DEFAULT_PAGE_LIMIT + 20) * interval_ms + 60_000
    result = fetch_historical_candles(
        transport,
        symbol="BTCUSDT",
        market_type="spot",
        interval="15",
        start_ms=base,
        end_ms=base + (DEFAULT_PAGE_LIMIT + 4) * interval_ms,
        now_ms=now,
        verify_symbol=True,
    )
    assert result.page_count >= 2
    starts = [c.start for c in result.candles]
    assert starts == sorted(starts)
    assert len(starts) == len(set(starts))
    assert "BYBIT PUBLIC" in result.provenance


def test_conflicting_duplicate_rejected() -> None:
    base = 1_700_000_000_000
    interval_ms = 15 * 60_000
    calls = {"n": 0}

    def handler(path: str, params: dict):
        if path.endswith("instruments-info"):
            return {
                "retCode": 0,
                "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading"}]},
            }
        calls["n"] += 1
        if calls["n"] == 1:
            rows = [_row(base + i * interval_ms) for i in range(DEFAULT_PAGE_LIMIT)]
            return {"retCode": 0, "result": {"list": list(reversed(rows))}}
        # Overlap last start with different OHLC
        conflict_start = base + (DEFAULT_PAGE_LIMIT - 1) * interval_ms
        return {
            "retCode": 0,
            "result": {
                "list": [
                    _row(conflict_start + interval_ms),
                    [conflict_start, "999", "1000", "998", "999.5", "1"],
                ]
            },
        }

    transport = FakeHistoryTransport(handler)
    now = base + (DEFAULT_PAGE_LIMIT + 10) * interval_ms + 60_000
    with pytest.raises(HistoryProviderError) as exc:
        fetch_historical_candles(
            transport,
            symbol="BTCUSDT",
            market_type="spot",
            interval="15",
            start_ms=base,
            end_ms=base + (DEFAULT_PAGE_LIMIT + 2) * interval_ms,
            now_ms=now,
        )
    assert exc.value.code == "conflicting_duplicate"


def test_invalid_ohlc_rejected() -> None:
    base = 1_700_000_000_000

    def handler(path: str, params: dict):
        if path.endswith("instruments-info"):
            return {
                "retCode": 0,
                "result": {"list": [{"symbol": "ETHUSDT", "status": "Trading"}]},
            }
        return {
            "retCode": 0,
            "result": {"list": [[base, "100", "90", "95", "96", "1"]]},  # high < low
        }

    with pytest.raises(HistoryProviderError) as exc:
        fetch_historical_candles(
            FakeHistoryTransport(handler),
            symbol="ETHUSDT",
            market_type="spot",
            interval="15",
            start_ms=base,
            end_ms=base + 15 * 60_000,
            now_ms=base + 20 * 60_000,
        )
    assert exc.value.code in {"invalid_ohlc", "malformed_ohlcv"} or "invalid" in exc.value.code


def test_incomplete_candle_dropped() -> None:
    base = 1_700_000_000_000
    interval_ms = 15 * 60_000

    def handler(path: str, params: dict):
        if path.endswith("instruments-info"):
            return {
                "retCode": 0,
                "result": {"list": [{"symbol": "SOLUSDT", "status": "Trading"}]},
            }
        # Only forming / incomplete relative to now
        return {"retCode": 0, "result": {"list": [_row(base)]}}

    # now before close+grace → empty → error
    with pytest.raises(HistoryProviderError) as exc:
        fetch_historical_candles(
            FakeHistoryTransport(handler),
            symbol="SOLUSDT",
            market_type="linear",
            interval="15",
            start_ms=base,
            end_ms=base,
            now_ms=base + interval_ms // 2,
            grace_ms=2000,
        )
    assert exc.value.code == "empty_dataset"


def test_cache_integrity_and_hash_stability(tmp_path: Path) -> None:
    candles = synthetic_trend_candles(n=40)
    h1 = candle_content_hash(candles)
    saved = save_dataset_cache(
        candles,
        meta={
            "symbol": "BTCUSDT",
            "interval": "15",
            "market_type": "spot",
            "provenance": "OFFLINE HISTORICAL FIXTURE",
            "label": "OFFLINE HISTORICAL FIXTURE",
        },
        datasets_dir=tmp_path,
    )
    assert saved.content_hash == h1
    loaded = load_dataset_cache(
        h1,
        datasets_dir=tmp_path,
        expected={"symbol": "BTCUSDT", "interval": "15", "market_type": "spot"},
    )
    assert candle_content_hash(loaded.candles) == h1

    # Corrupt body
    path = tmp_path / f"{h1}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["candles"][0]["close"] = 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatasetCacheError) as exc:
        load_dataset_cache(h1, datasets_dir=tmp_path)
    assert exc.value.code == "hash_mismatch"


def test_cache_identity_mismatch(tmp_path: Path) -> None:
    candles = synthetic_trend_candles(n=20)
    saved = save_dataset_cache(
        candles,
        meta={"symbol": "BTCUSDT", "interval": "15", "market_type": "spot"},
        datasets_dir=tmp_path,
    )
    with pytest.raises(DatasetCacheError) as exc:
        load_dataset_cache(
            saved.content_hash,
            datasets_dir=tmp_path,
            expected={"symbol": "ETHUSDT", "interval": "15", "market_type": "spot"},
        )
    assert exc.value.code == "identity_mismatch"
