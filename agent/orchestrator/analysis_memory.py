"""Remember the latest orchestrator analysis so LIVE intake can reuse side/SL/TP."""

from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_LAST: dict[str, Any] | None = None
_TTL_MS = 30 * 60_000


def remember_analysis(body: dict[str, Any]) -> None:
    """Store a compact snapshot of the latest full analysis."""
    global _LAST
    if not isinstance(body, dict):
        return
    symbol = str(body.get("symbol") or "").upper()
    if not symbol:
        return
    side = str(body.get("side") or body.get("analysis_action") or body.get("action") or "").upper()
    if side in {"LONG"}:
        side = "BUY"
    elif side in {"SHORT"}:
        side = "SELL"
    if side not in {"BUY", "SELL"}:
        side = ""
    now = int(time.time() * 1000)
    snap = {
        "symbol": symbol,
        "category": str(body.get("category") or "linear"),
        "side": side or None,
        "entry": body.get("entry"),
        "stop_loss": body.get("stop_loss"),
        "take_profit": body.get("take_profit"),
        "last_price": body.get("last_price"),
        "analysis_action": str(body.get("analysis_action") or body.get("action") or ""),
        "stored_ms": now,
        "expires_ms": now + _TTL_MS,
    }
    with _LOCK:
        _LAST = snap


def latest_analysis(*, symbol: str | None = None) -> dict[str, Any] | None:
    global _LAST
    with _LOCK:
        if _LAST is None:
            return None
        now = int(time.time() * 1000)
        if now >= int(_LAST.get("expires_ms") or 0):
            _LAST = None
            return None
        if symbol:
            want = str(symbol).upper()
            if not want.endswith("USDT") and len(want) <= 10:
                want = f"{want}USDT"
            if str(_LAST.get("symbol") or "").upper() != want:
                return None
        return dict(_LAST)


def reset_analysis_memory_for_tests() -> None:
    global _LAST
    with _LOCK:
        _LAST = None
