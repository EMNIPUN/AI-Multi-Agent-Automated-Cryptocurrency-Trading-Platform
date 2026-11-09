"""Paper supervisor runtime. Starts only when CRYPTONOVA_PAPER_SUPERVISOR is on."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from agent.market_data import Candle
from agent.supervisor.worker import PaperSupervisorWorker
from apps.api.app.orchestrator.router import get_supervisor, reset_supervisor_for_tests

logger = logging.getLogger(__name__)

_WORKER: PaperSupervisorWorker | None = None


def _enabled() -> bool:
    from apps.api.app.orchestrator.router import _enabled as router_enabled

    return router_enabled()


def _fetch_public_candles(
    *,
    symbol: str,
    category: str,
    interval: str,
    limit: int,
    now_ms: int,
) -> list[Candle]:
    from apps.api.app.market_data.rest_client import BybitPublicRestClient, HttpxPublicTransport
    from apps.api.app.market_data.schemas import MarketCategory

    transport = HttpxPublicTransport()
    try:
        client = BybitPublicRestClient(transport)
        kl = client.get_klines(
            category=MarketCategory(category),
            symbol=symbol,
            interval=interval,
            limit=limit,
            now_ms=now_ms,
        )
        return [
            Candle(
                start=int(bar.time) * 1000,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume),
            )
            for bar in kl.candles
        ]
    finally:
        transport.close()


def maybe_start_paper_supervisor_worker() -> None:
    global _WORKER
    if not _enabled():
        return
    supervisor = get_supervisor()
    if supervisor is None:
        return
    if _WORKER is not None and _WORKER.running:
        return
    # API restart must not wait out a dead owner's lease heartbeat.
    try:
        adopted = supervisor.adopt_lease()
        logger.info(
            "paper_supervisor_lease_adopted owner=%s previous=%s",
            adopted.get("owner"),
            adopted.get("previous_owner"),
        )
    except Exception:  # noqa: BLE001 — worker should still start; ticks may skip if busy
        logger.exception("paper_supervisor_lease_adopt_failed")
    _WORKER = PaperSupervisorWorker(supervisor, fetch_candles=_fetch_public_candles)
    _WORKER.start()
    logger.info("paper_supervisor_worker_started mode=PAPER live_orders=false")


def shutdown_paper_supervisor_worker() -> None:
    global _WORKER
    if _WORKER is not None:
        _WORKER.stop()
        _WORKER = None
    reset_supervisor_for_tests()


def worker_status() -> dict[str, Any]:
    worker = _WORKER
    return {
        "worker_running": bool(worker and worker.running),
        "last_cycle": (worker.last_cycle if worker else {}),
        "live_orders": False,
        "exchange_order_sent": False,
        "polled_at_ms": int(time.time() * 1000),
    }


def set_worker_for_tests(worker: PaperSupervisorWorker | None) -> None:
    global _WORKER
    _WORKER = worker
