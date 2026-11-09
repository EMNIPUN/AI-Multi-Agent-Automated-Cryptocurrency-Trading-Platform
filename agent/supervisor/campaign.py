"""HYPEUSDT autonomous paper campaign harness.

Tracks a 48-hour PAPER session against public market candles when run live.
Does not claim completion until wall-clock duration elapses.
Never places exchange orders.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from agent.market_data import Candle
from agent.paper.config import PaperBrokerConfig
from agent.supervisor.feasibility import evaluate_hype_feasibility
from agent.supervisor.machine import PaperSupervisor


CandleFetcher = Callable[..., list[Candle]]


@dataclass
class CampaignConfig:
    symbol: str = "HYPEUSDT"
    category: str = "linear"
    interval: str = "15"
    capital_usdt: Decimal = Decimal("5")
    risk_fraction: Decimal = Decimal("0.01")
    duration_hours: int = 48
    poll_seconds: float = 30.0
    journal_path: str = "data/paper_campaign/hype_48h.sqlite3"
    report_path: str = "data/paper_campaign/hype_48h_report.json"
    profit_target_usdt: Decimal = Decimal("3")
    profit_target_is_requirement: bool = False


@dataclass
class CampaignCounters:
    cycles: int = 0
    confirmed_candles_seen: int = 0
    hold_count: int = 0
    blocked_count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    flat_budget_count: int = 0
    duplicate_candle_count: int = 0
    errors: list[str] = field(default_factory=list)
    restart_events: int = 0


class PaperCampaign:
    def __init__(
        self,
        config: CampaignConfig | None = None,
        *,
        fetch_candles: CandleFetcher | None = None,
        evaluate: Callable[..., Any] | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.config = config or CampaignConfig()
        self.fetch_candles = fetch_candles
        self.evaluate = evaluate
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self.counters = CampaignCounters()
        self.started_at_ms = 0
        self.ends_at_ms = 0
        self._supervisor: PaperSupervisor | None = None

    def _supervisor_open(self) -> PaperSupervisor:
        if self._supervisor is None:
            broker = PaperBrokerConfig(
                initial_balance=self.config.capital_usdt,
                max_total_exposure=self.config.capital_usdt,
            )
            self._supervisor = PaperSupervisor(
                self.config.journal_path,
                broker,
                evaluate=self.evaluate,
                worker_token="campaign-worker",
            )
        return self._supervisor

    def start(self) -> dict[str, Any]:
        now = self._now_ms()
        self.started_at_ms = now
        self.ends_at_ms = now + self.config.duration_hours * 3_600_000
        supervisor = self._supervisor_open()
        started = supervisor.command(
            "start",
            now_ms=now,
            authorization={
                "symbol": self.config.symbol,
                "category": self.config.category,
                "interval": self.config.interval,
                "capital_usdt": str(self.config.capital_usdt),
                "risk_fraction": str(self.config.risk_fraction),
                "duration_hours": self.config.duration_hours,
                "started_at_ms": now,
                "expires_at_ms": self.ends_at_ms,
            },
        )
        body = self.status()
        body["supervisor"] = started
        self._write_report(body)
        return body

    def resume_after_restart(self) -> dict[str, Any]:
        self.counters.restart_events += 1
        self._supervisor = None
        supervisor = self._supervisor_open()
        status = supervisor.status()
        if status.get("state") != "RUNNING":
            return self.start()
        auth = status.get("authorization") if isinstance(status.get("authorization"), dict) else {}
        self.started_at_ms = int(auth.get("started_at_ms") or self._now_ms())
        self.ends_at_ms = int(auth.get("expires_at_ms") or (self.started_at_ms + self.config.duration_hours * 3_600_000))
        body = self.status()
        body["resumed"] = True
        self._write_report(body)
        return body

    def tick_once(self) -> dict[str, Any]:
        now = self._now_ms()
        if self.started_at_ms and now >= self.ends_at_ms:
            return self.finalize(reason="duration_elapsed")
        supervisor = self._supervisor_open()
        if self.fetch_candles is None:
            raise RuntimeError("campaign_candle_fetcher_missing")
        try:
            candles = self.fetch_candles(
                symbol=self.config.symbol,
                category=self.config.category,
                interval=self.config.interval,
                limit=220,
                now_ms=now,
            )
        except Exception as exc:  # noqa: BLE001
            self.counters.errors.append(type(exc).__name__)
            result = supervisor.run_cycle(
                [],
                symbol=self.config.symbol,
                category=self.config.category,
                interval=self.config.interval,
                now_ms=now,
                data_fresh=False,
            )
            self.counters.cycles += 1
            self._write_report(self.status(last_cycle=result))
            return result

        if candles:
            self.counters.confirmed_candles_seen = max(
                self.counters.confirmed_candles_seen, len(candles)
            )
            price = Decimal(str(candles[-1].close))
            feasibility = evaluate_hype_feasibility(
                price=price,
                capital=self.config.capital_usdt,
                risk_fraction=self.config.risk_fraction,
            )
        else:
            feasibility = {"feasible": False, "reason_code": "NO_CANDLES"}

        result = supervisor.run_cycle(
            candles,
            symbol=self.config.symbol,
            category=self.config.category,
            interval=self.config.interval,
            now_ms=now,
            data_fresh=bool(candles),
        )
        self.counters.cycles += 1
        action = str(result.get("analysis_action") or result.get("last_action") or "")
        reason = str(result.get("reason") or "")
        if reason == "duplicate_candle":
            self.counters.duplicate_candle_count += 1
        elif reason == "FLAT_BUDGET":
            self.counters.flat_budget_count += 1
            self.counters.hold_count += 1
        elif action == "BUY":
            self.counters.buy_count += 1
        elif action == "SELL":
            self.counters.sell_count += 1
        elif action == "BLOCKED":
            self.counters.blocked_count += 1
        else:
            self.counters.hold_count += 1
        if result.get("last_error"):
            self.counters.errors.append(str(result["last_error"]))
        body = self.status(last_cycle=result, feasibility=feasibility)
        self._write_report(body)
        return body

    def run_until(
        self,
        *,
        max_ticks: int | None = None,
        sleep: bool = True,
    ) -> dict[str, Any]:
        ticks = 0
        while True:
            now = self._now_ms()
            if self.ends_at_ms and now >= self.ends_at_ms:
                return self.finalize(reason="duration_elapsed")
            if max_ticks is not None and ticks >= max_ticks:
                body = self.status()
                body["campaign_status"] = "IN_PROGRESS"
                body["stopped_reason"] = "max_ticks"
                self._write_report(body)
                return body
            self.tick_once()
            ticks += 1
            if sleep and self.config.poll_seconds > 0:
                time.sleep(self.config.poll_seconds)

    def finalize(self, *, reason: str) -> dict[str, Any]:
        body = self.status()
        elapsed = max(0, self._now_ms() - self.started_at_ms) if self.started_at_ms else 0
        complete = elapsed >= self.config.duration_hours * 3_600_000
        body["campaign_status"] = "COMPLETE_AND_VERIFIED" if complete else "IMPLEMENTED_BUT_UNVERIFIED"
        body["stopped_reason"] = reason
        body["wall_clock_complete"] = complete
        body["profit_target_usdt"] = str(self.config.profit_target_usdt)
        body["profit_target_is_requirement"] = False
        body["live_orders"] = False
        body["exchange_order_sent"] = False
        self._write_report(body)
        return body

    def status(self, **extra: Any) -> dict[str, Any]:
        now = self._now_ms()
        report: dict[str, Any] = {}
        try:
            report = self._supervisor_open().report()
        except Exception as exc:  # noqa: BLE001
            report = {"error": type(exc).__name__, "live_orders": False}
        # Hydrate timers from durable authorization when this process did not call start().
        if not self.started_at_ms or not self.ends_at_ms:
            auth = report.get("authorization") if isinstance(report.get("authorization"), dict) else {}
            self.started_at_ms = int(auth.get("started_at_ms") or self.started_at_ms or 0)
            self.ends_at_ms = int(auth.get("expires_at_ms") or self.ends_at_ms or 0)
        elapsed_ms = max(0, now - self.started_at_ms) if self.started_at_ms else 0
        remaining_ms = max(0, self.ends_at_ms - now) if self.ends_at_ms else 0
        if not self.started_at_ms:
            campaign_status = "NOT_STARTED"
            wall_clock_complete = False
        elif remaining_ms > 0:
            campaign_status = "IN_PROGRESS"
            wall_clock_complete = False
        else:
            # Duration elapsed in wall clock — still require finalize() evidence for verified.
            campaign_status = "IMPLEMENTED_BUT_UNVERIFIED"
            wall_clock_complete = True
        body = {
            "symbol": self.config.symbol,
            "category": self.config.category,
            "interval": self.config.interval,
            "mode": "PAPER",
            "capital_usdt": str(self.config.capital_usdt),
            "risk_fraction": str(self.config.risk_fraction),
            "duration_hours": self.config.duration_hours,
            "started_at_ms": self.started_at_ms,
            "ends_at_ms": self.ends_at_ms,
            "elapsed_ms": elapsed_ms,
            "remaining_ms": remaining_ms,
            "started_at_utc": _fmt(self.started_at_ms),
            "ends_at_utc": _fmt(self.ends_at_ms),
            "campaign_status": campaign_status,
            "wall_clock_complete": wall_clock_complete,
            "profit_target_is_requirement": False,
            "funding": "unsupported",
            "shorting": "unsupported",
            "liquidation": "unsupported",
            "live_orders": False,
            "execution_allowed": False,
            "exchange_order_sent": False,
            "counters": asdict(self.counters),
            "paper_report": report,
        }
        body.update(extra)
        return body

    def _write_report(self, body: dict[str, Any]) -> None:
        path = Path(self.config.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")


def _fmt(ms: int) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def default_public_fetcher(
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
