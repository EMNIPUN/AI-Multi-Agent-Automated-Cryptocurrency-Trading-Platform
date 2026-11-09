"""Evaluate signals from fixtures or public market REST — never private APIs."""

from __future__ import annotations

import time
from pathlib import Path

from agent.market_data import Candle
from agent.multi_agent.config import STRATEGY_VERSION, SignalPipelineConfig
from agent.multi_agent.pipeline import SignalPipeline, blocked_shell
from agent.multi_agent.risk_agent import SignalRiskState
from agent.multi_agent.signal_history_store import (
    SignalHistoryStore,
    resolve_signal_db_path,
)
from agent.multi_agent.types import CoordinatorDecision
from apps.api.app.market_data.constants import DEFAULT_SYMBOLS
from apps.api.app.market_data.rest_client import BybitPublicRestClient
from apps.api.app.market_data.schemas import MarketCategory
from apps.api.app.signals.schemas import CandleIn

_DEFAULT_SIGNAL_DB = resolve_signal_db_path()

_store: SignalHistoryStore | None = None
_pipeline: SignalPipeline | None = None


def get_signal_store() -> SignalHistoryStore:
    global _store
    if _store is None:
        try:
            _store = SignalHistoryStore(resolve_signal_db_path())
        except RuntimeError as exc:
            message = str(exc)
            if (
                "signal_cloud_owner_user_id_unset" in message
                or "cryptonova_test_owner_user_id_invalid_uuid" in message
            ):
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "signal_owner_unconfigured",
                        "message": (
                            "Signal persistence has no authenticated owner and no approved "
                            "operator binding. No owner id was invented."
                        ),
                        "execution_allowed": False,
                    },
                ) from None
            raise
    return _store


def get_signal_pipeline() -> SignalPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SignalPipeline(
            config=SignalPipelineConfig(),
            history_store=get_signal_store(),
            persist=True,
        )
    return _pipeline


def reset_signal_pipeline_for_tests(
    *,
    db_path: str | Path | None = None,
    persist: bool = False,
) -> SignalPipeline:
    global _pipeline, _store
    _store = SignalHistoryStore(db_path) if db_path is not None else None
    _pipeline = SignalPipeline(
        config=SignalPipelineConfig(),
        risk_state=SignalRiskState(),
        history_store=_store,
        persist=persist and _store is not None,
    )
    return _pipeline


def _to_candles(rows: list[CandleIn]) -> list[Candle]:
    return [
        Candle(
            start=int(r.start),
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=float(r.volume),
        )
        for r in rows
    ]


def evaluate_from_candles(
    *,
    symbol: str,
    category: str,
    interval: str,
    candles: list[CandleIn],
    now_ms: int | None,
    data_path: str,
) -> CoordinatorDecision:
    sym = symbol.upper()
    if sym not in DEFAULT_SYMBOLS:
        return blocked_shell(
            symbol=sym,
            category=category,
            interval=interval,
            now_ms=now_ms or int(time.time() * 1000),
            reason="SYMBOL_NOT_ALLOWLISTED",
        )
    return get_signal_pipeline().evaluate(
        symbol=sym,
        category=category,
        interval=interval,
        candles=_to_candles(candles),
        now_ms=now_ms if now_ms is not None else int(time.time() * 1000),
        data_path=data_path,
    )


def evaluate_from_public_rest(
    *,
    client: BybitPublicRestClient,
    symbol: str,
    category: str,
    interval: str,
) -> CoordinatorDecision:
    """Pull public klines only — no API keys, no wallet, no orders."""
    sym = symbol.upper()
    if sym not in DEFAULT_SYMBOLS:
        return blocked_shell(
            symbol=sym,
            category=category,
            interval=interval,
            now_ms=int(time.time() * 1000),
            reason="SYMBOL_NOT_ALLOWLISTED",
        )
    cat = MarketCategory(category)
    kl = client.get_klines(category=cat, symbol=sym, interval=interval, limit=250)
    candles = [
        Candle(
            start=int(b.time) * 1000,
            open=float(b.open),
            high=float(b.high),
            low=float(b.low),
            close=float(b.close),
            volume=float(b.volume),
        )
        for b in kl.candles
    ]
    now_ms = int(time.time() * 1000)
    return get_signal_pipeline().evaluate(
        symbol=sym,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=now_ms,
        data_path=kl.data_path or "public_rest_only",
    )


def strategy_status_fields() -> dict[str, str]:
    return {
        "strategy_version": STRATEGY_VERSION,
        "phase": "4C",
        "storage": str(resolve_signal_db_path()),
        "auto_engine": "signals_only",
    }
