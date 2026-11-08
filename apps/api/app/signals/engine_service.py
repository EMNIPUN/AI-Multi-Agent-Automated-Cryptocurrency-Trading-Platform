"""Process-local Phase 4C automatic signal engine singleton."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable

from agent.multi_agent.auto_engine import (
    AUTO_ENGINE_VERSION,
    AutoSignalEngine,
    AutoSignalEngineConfig,
    RestKlineFetcher,
)
from agent.multi_agent.config import STRATEGY_VERSION
from apps.api.app.market_data.constants import DEFAULT_SYMBOLS, SUPPORTED_INTERVALS
from apps.api.app.market_data.rest_client import BybitPublicRestClient
from apps.api.app.market_data.schemas import MarketCategory
from apps.api.app.market_data.ws_manager import PublicMarketWsManager
from apps.api.app.signals.service import get_signal_pipeline, get_signal_store

_engine: AutoSignalEngine | None = None
_engine_lock = threading.RLock()
_ws_managers: list[PublicMarketWsManager] = []


def _parse_symbols() -> tuple[str, ...]:
    raw = os.getenv("SIGNAL_AUTO_SYMBOLS") or os.getenv("AGENT_SYMBOLS") or ""
    if raw.strip():
        syms = [s.strip().upper() for s in raw.split(",") if s.strip()]
        allow = {s.upper() for s in DEFAULT_SYMBOLS}
        extra = os.getenv("MARKET_PUBLIC_SYMBOLS", "").strip()
        if extra:
            allow |= {s.strip().upper() for s in extra.split(",") if s.strip()}
        filtered = tuple(s for s in syms if s in allow)
        if filtered:
            return filtered
    return ("BTCUSDT",)


def _parse_interval() -> str:
    raw = (os.getenv("SIGNAL_AUTO_INTERVAL") or os.getenv("AGENT_INTERVAL") or "15").strip()
    return raw if raw in SUPPORTED_INTERVALS else "15"


def _parse_category() -> str:
    raw = (os.getenv("SIGNAL_AUTO_CATEGORY") or os.getenv("AGENT_CATEGORY") or "linear").strip()
    return raw if raw in {"spot", "linear"} else "linear"


def _autoload_enabled() -> bool:
    return os.getenv("SIGNAL_AUTO_ENGINE_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _build_ws_start(
    *,
    category: str,
    symbols: tuple[str, ...],
    interval: str,
    connect_fn: Any | None = None,
) -> Callable[[Callable[[dict[str, Any]], None]], Callable[[], None]]:
    def start_ws(on_event: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        from apps.api.app.market_data.real_ws import connect_bybit_public

        cat = MarketCategory(category)
        mgr = PublicMarketWsManager(
            category=cat,
            symbols=list(symbols),
            intervals=[interval],
            connect_fn=connect_fn or connect_bybit_public,
            on_event=on_event,
        )
        mgr.start()
        _ws_managers.append(mgr)

        def stop() -> None:
            try:
                mgr.stop()
            finally:
                if mgr in _ws_managers:
                    _ws_managers.remove(mgr)

        return stop

    return start_ws


def get_auto_engine(
    *,
    rest_client: BybitPublicRestClient | None = None,
    connect_fn: Any | None = None,
) -> AutoSignalEngine:
    global _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        store = get_signal_store()
        pipeline = get_signal_pipeline()
        client = rest_client
        if client is None:
            from apps.api.app.market_data.rest_client import (
                FakePublicTransport,
                HttpxPublicTransport,
            )

            simulated = os.getenv("MARKET_DATA_SIMULATED", "false").strip().lower() in {
                "1",
                "true",
                "yes",
            }
            if simulated:
                client = BybitPublicRestClient(FakePublicTransport({}), simulated=True)
            else:
                client = BybitPublicRestClient(HttpxPublicTransport(), simulated=False)
        cfg = AutoSignalEngineConfig(
            symbols=_parse_symbols(),
            category=_parse_category(),
            interval=_parse_interval(),
            strategy_version=STRATEGY_VERSION,
            enabled_on_start=_autoload_enabled(),
        )
        _engine = AutoSignalEngine(
            pipeline=pipeline,
            store=store,
            fetcher=RestKlineFetcher(client),
            config=cfg,
            ws_start_fn=_build_ws_start(
                category=cfg.category,
                symbols=cfg.symbols,
                interval=cfg.interval,
                connect_fn=connect_fn,
            ),
        )
        return _engine


def reset_auto_engine_for_tests(
    engine: AutoSignalEngine | None = None,
) -> AutoSignalEngine | None:
    global _engine
    with _engine_lock:
        if _engine is not None:
            try:
                _engine.stop()
            except Exception:  # noqa: BLE001
                pass
        for mgr in list(_ws_managers):
            try:
                mgr.stop()
            except Exception:  # noqa: BLE001
                pass
        _ws_managers.clear()
        _engine = engine
        return _engine


def start_auto_engine(*, rest_client: BybitPublicRestClient | None = None) -> dict[str, Any]:
    eng = get_auto_engine(rest_client=rest_client)
    return eng.start()


def stop_auto_engine() -> dict[str, Any]:
    with _engine_lock:
        if _engine is None:
            return {
                "state": "stopped",
                "engine_version": AUTO_ENGINE_VERSION,
                "execution_allowed": False,
                "trading_enabled": False,
                "note": "Engine not started",
            }
        return _engine.stop()


def auto_engine_status() -> dict[str, Any]:
    with _engine_lock:
        if _engine is None:
            return {
                "state": "stopped",
                "engine_version": AUTO_ENGINE_VERSION,
                "strategy_version": STRATEGY_VERSION,
                "execution_allowed": False,
                "trading_enabled": False,
                "private_api_used": False,
                "not_automatic_trading": True,
                "autoload": _autoload_enabled(),
                "configured_symbols": list(_parse_symbols()),
                "configured_interval": _parse_interval(),
                "configured_category": _parse_category(),
                "note": "Automatic SIGNAL evaluation only — never automatic trading",
            }
        out = _engine.status()
        out["autoload"] = _autoload_enabled()
        return out


def maybe_autoload_engine() -> None:
    """Called from FastAPI lifespan — opt-in via SIGNAL_AUTO_ENGINE_ENABLED."""
    if not _autoload_enabled():
        return
    try:
        start_auto_engine()
    except Exception as exc:  # noqa: BLE001
        print(f"[signals-auto] autoload_failed error={type(exc).__name__}")


def shutdown_auto_engine() -> None:
    try:
        stop_auto_engine()
    except Exception:  # noqa: BLE001
        pass
