"""
Public Bybit historical OHLCV loader for Prompt 68C.

Uses only official public REST endpoints. No API keys. No private trading routes.
Pagination walks start→end with overlapping-boundary dedupe. Never synthesizes gaps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from agent.backtest.limits import (
    DEFAULT_HTTP_MAX_RETRIES,
    DEFAULT_HTTP_MIN_INTERVAL_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_MAX_CANDLES_PER_RUN,
    DEFAULT_MAX_RANGE_MS,
    DEFAULT_PAGE_LIMIT,
    RUN_UI_INTERVALS,
    RUN_UI_MARKET_TYPES,
    RUN_UI_SYMBOLS,
)
from agent.backtest.validation import CandleValidationError, validate_ohlc_candle
from agent.candle_time import CandleTimeError, assert_supported_interval, candle_close_ms
from agent.market_data import Candle

BYBIT_PUBLIC_REST_BASE = "https://api.bybit.com"
KLINE_PATH = "/v5/market/kline"
INSTRUMENTS_PATH = "/v5/market/instruments-info"
PROVENANCE_LABEL = "HISTORICAL BYBIT PUBLIC MARKET DATA"


class HistoryProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PublicHttpTransport(Protocol):
    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]: ...


class HttpxHistoryTransport:
    """Bounded public REST transport with soft rate limit + retries."""

    def __init__(
        self,
        *,
        base_url: str = BYBIT_PUBLIC_REST_BASE,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        min_interval_s: float = DEFAULT_HTTP_MIN_INTERVAL_SECONDS,
        max_retries: int = DEFAULT_HTTP_MAX_RETRIES,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._min_interval = min_interval_s
        self._max_retries = max(0, max_retries)
        self._last_call = 0.0

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            try:
                response = self._client.get(path, params=params)
                self._last_call = time.monotonic()
                if response.status_code == 429:
                    # Rate limited — exponential backoff then retry.
                    time.sleep(min(8.0, 0.4 * (2**attempt)))
                    last_exc = HistoryProviderError("rate_limited", "Bybit public rate limit")
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise HistoryProviderError("malformed_response", "non-object JSON")
                return payload
            except HistoryProviderError:
                raise
            except httpx.TimeoutException as exc:
                last_exc = HistoryProviderError("timeout", "public API timeout")
                time.sleep(min(8.0, 0.3 * (2**attempt)))
                if attempt >= self._max_retries:
                    raise last_exc from exc
            except httpx.HTTPError as exc:
                last_exc = HistoryProviderError("http_error", f"public API HTTP error: {exc}")
                time.sleep(min(8.0, 0.3 * (2**attempt)))
                if attempt >= self._max_retries:
                    raise last_exc from exc
        assert last_exc is not None
        raise last_exc

    def close(self) -> None:
        if self._owns:
            self._client.close()


class FakeHistoryTransport:
    """Deterministic in-memory transport for unit tests (no network)."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, dict(params)))
        return self._handler(path, dict(params))


@dataclass(frozen=True)
class HistoryFetchResult:
    candles: tuple[Candle, ...]
    symbol: str
    market_type: str
    interval: str
    start_ms: int
    end_ms: int
    provenance: str
    retrieved_ms: int
    page_count: int
    warnings: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


def estimate_candle_count(start_ms: int, end_ms: int, interval: str) -> int:
    """Upper-bound estimate of confirmed bars in [start, end] (no network)."""
    key = assert_supported_interval(interval)
    if not key.isdigit():
        # Calendar intervals — coarse estimate via ~1 day for D.
        step = {"D": 86_400_000, "W": 7 * 86_400_000, "M": 30 * 86_400_000}.get(key)
        if step is None:
            raise HistoryProviderError("unsupported_interval", f"unsupported interval {interval}")
    else:
        step = int(key) * 60_000
    if end_ms < start_ms:
        raise HistoryProviderError("invalid_range", "end_ms before start_ms")
    return max(0, int((end_ms - start_ms) // step) + 1)


def validate_history_request(
    *,
    symbol: str,
    market_type: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    max_candles: int = DEFAULT_MAX_CANDLES_PER_RUN,
    max_range_ms: int = DEFAULT_MAX_RANGE_MS,
    require_ui_allowlist: bool = True,
) -> tuple[str, str, str]:
    sym = (symbol or "").strip().upper()
    mt = (market_type or "").strip().lower()
    try:
        iv = assert_supported_interval(interval)
    except CandleTimeError as exc:
        raise HistoryProviderError("unsupported_interval", str(exc)) from exc
    if require_ui_allowlist and sym not in RUN_UI_SYMBOLS:
        raise HistoryProviderError("unsupported_symbol", f"symbol {sym} not in supported set")
    if mt not in RUN_UI_MARKET_TYPES:
        raise HistoryProviderError("unsupported_market_type", f"market_type must be spot|linear")
    if require_ui_allowlist and iv not in RUN_UI_INTERVALS:
        raise HistoryProviderError(
            "unsupported_interval",
            f"interval {iv} not in UI-supported set {sorted(RUN_UI_INTERVALS)}",
        )
    if not isinstance(start_ms, int) or not isinstance(end_ms, int):
        raise HistoryProviderError("invalid_range", "start_ms/end_ms must be int UTC ms")
    if start_ms <= 0 or end_ms <= 0:
        raise HistoryProviderError("invalid_range", "timestamps must be positive")
    if start_ms > end_ms:
        raise HistoryProviderError("invalid_range", "start_ms cannot exceed end_ms")
    now_ms = int(time.time() * 1000)
    if end_ms > now_ms:
        raise HistoryProviderError("future_range", "end_ms must not be in the future")
    span = end_ms - start_ms
    if span > max_range_ms:
        raise HistoryProviderError(
            "range_too_large",
            f"requested range {span}ms exceeds max {max_range_ms}ms",
        )
    est = estimate_candle_count(start_ms, end_ms, iv)
    if est > max_candles:
        raise HistoryProviderError(
            "too_many_candles",
            f"estimated {est} candles exceeds max {max_candles}",
        )
    return sym, mt, iv


def _parse_kline_row(row: Any) -> Candle | None:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        return None
    try:
        start = int(row[0])
        o = float(row[1])
        h = float(row[2])
        low = float(row[3])
        c = float(row[4])
        v = float(row[5])
    except (TypeError, ValueError):
        return None
    return Candle(start=start, open=o, high=h, low=low, close=c, volume=v)


def _require_ok(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("retCode") != 0:
        raise HistoryProviderError(
            "bybit_error",
            str(payload.get("retMsg") or "bybit_error"),
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise HistoryProviderError("malformed_result", "missing result object")
    return result


def verify_instrument(
    transport: PublicHttpTransport,
    *,
    symbol: str,
    market_type: str,
) -> None:
    """Confirm symbol exists on public instruments-info (Trading status)."""
    payload = transport.get(
        INSTRUMENTS_PATH,
        {"category": market_type, "symbol": symbol},
    )
    result = _require_ok(payload)
    rows = result.get("list") or []
    if not isinstance(rows, list) or not rows:
        raise HistoryProviderError("unsupported_symbol", f"{symbol} not listed for {market_type}")
    row = rows[0] if isinstance(rows[0], dict) else {}
    status = str(row.get("status") or "")
    if status and status not in {"Trading", "PreLaunch"}:
        raise HistoryProviderError(
            "unsupported_symbol",
            f"{symbol} status={status} is not tradeable for research data",
        )


def fetch_historical_candles(
    transport: PublicHttpTransport,
    *,
    symbol: str,
    market_type: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    grace_ms: int = 2_000,
    max_candles: int = DEFAULT_MAX_CANDLES_PER_RUN,
    max_range_ms: int = DEFAULT_MAX_RANGE_MS,
    require_ui_allowlist: bool = True,
    verify_symbol: bool = True,
    now_ms: int | None = None,
) -> HistoryFetchResult:
    """
    Paginate Bybit public klines from start_ms through end_ms (inclusive starts).

    - Newest page returned by Bybit is newest-first; we reverse per page.
    - Walks forward using the last accepted start + 1ms as the next `start`.
    - Rejects conflicting duplicates; identical duplicates are skipped.
    - Drops incomplete / still-forming bars using close+grace.
    """
    sym, mt, iv = validate_history_request(
        symbol=symbol,
        market_type=market_type,
        interval=interval,
        start_ms=start_ms,
        end_ms=end_ms,
        max_candles=max_candles,
        max_range_ms=max_range_ms,
        require_ui_allowlist=require_ui_allowlist,
    )
    if verify_symbol:
        verify_instrument(transport, symbol=sym, market_type=mt)

    clock = now_ms if now_ms is not None else int(time.time() * 1000)
    retrieved_ms = clock
    by_start: dict[int, Candle] = {}
    page_count = 0
    warnings: list[str] = []
    cursor = int(start_ms)
    hard_end = int(end_ms)

    while cursor <= hard_end:
        page_count += 1
        if page_count > 200:
            raise HistoryProviderError("pagination_limit", "too many pages — aborting")
        payload = transport.get(
            KLINE_PATH,
            {
                "category": mt,
                "symbol": sym,
                "interval": iv,
                "start": cursor,
                "end": hard_end,
                "limit": DEFAULT_PAGE_LIMIT,
            },
        )
        result = _require_ok(payload)
        rows = result.get("list") or []
        if not isinstance(rows, list) or not rows:
            break

        # Bybit returns newest first within the page.
        page_candles: list[Candle] = []
        for row in reversed(rows):
            c = _parse_kline_row(row)
            if c is None:
                raise HistoryProviderError("malformed_ohlcv", "unparseable kline row")
            try:
                validate_ohlc_candle(c)
            except CandleValidationError as exc:
                raise HistoryProviderError(exc.code, exc.message) from exc
            close_ms = candle_close_ms(int(c.start), iv)
            # Confirmed-only with grace — never treat forming bar as historical evidence.
            if clock < close_ms + int(grace_ms):
                continue
            if int(c.start) < start_ms or int(c.start) > hard_end:
                continue
            page_candles.append(c)

        if not page_candles:
            break

        for c in page_candles:
            prev = by_start.get(int(c.start))
            if prev is None:
                by_start[int(c.start)] = c
                continue
            if (
                prev.open == c.open
                and prev.high == c.high
                and prev.low == c.low
                and prev.close == c.close
                and prev.volume == c.volume
            ):
                continue
            raise HistoryProviderError(
                "conflicting_duplicate",
                f"conflicting candle at start={c.start}",
            )

        if len(by_start) > max_candles:
            raise HistoryProviderError(
                "too_many_candles",
                f"fetched {len(by_start)} candles exceeds max {max_candles}",
            )

        last_start = max(int(c.start) for c in page_candles)
        next_cursor = last_start + 1
        if next_cursor <= cursor:
            # Defensive — avoid infinite loop if exchange repeats the same window.
            warnings.append("pagination_stalled")
            break
        cursor = next_cursor
        if len(page_candles) < DEFAULT_PAGE_LIMIT and last_start >= hard_end:
            break
        # If page was full but last bar still before end, continue; if short page, stop.
        if len(rows) < DEFAULT_PAGE_LIMIT:
            break

    ordered = tuple(by_start[k] for k in sorted(by_start))
    if not ordered:
        raise HistoryProviderError("empty_dataset", "no confirmed candles in requested range")

    return HistoryFetchResult(
        candles=ordered,
        symbol=sym,
        market_type=mt,
        interval=iv,
        start_ms=start_ms,
        end_ms=end_ms,
        provenance=PROVENANCE_LABEL,
        retrieved_ms=retrieved_ms,
        page_count=page_count,
        warnings=tuple(warnings),
        meta={
            "endpoint": KLINE_PATH,
            "base_url": BYBIT_PUBLIC_REST_BASE,
            "grace_ms": grace_ms,
            "candle_count": len(ordered),
            "first_start_ms": int(ordered[0].start),
            "last_start_ms": int(ordered[-1].start),
        },
    )
