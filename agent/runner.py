import time
from datetime import datetime, timezone

from pybit.unified_trading import HTTP

from agent.config import AgentSettings, live_orders_blocked
from agent.executor import OrderExecutor
from agent.journal import TradeJournal
from agent.market_data import fetch_candles, get_equity, get_position
from agent.risk import RiskManager
from agent.strategies.ema_rsi import EmaRsiStrategy
from bot.config import env_label, is_live_mainnet


class AgentRunner:
    def __init__(self, session: HTTP, settings: AgentSettings) -> None:
        self.session = session
        self.settings = settings
        self.strategy = EmaRsiStrategy(settings)
        self.risk = RiskManager(settings)
        self.journal = TradeJournal()
        self.executor = OrderExecutor(session, settings, self.journal)

    def _status_line(self, equity: float | None) -> None:
        mode = "DRY-RUN" if self.settings.dry_run else "LIVE-ORDERS"
        if live_orders_blocked(self.settings) and not self.settings.dry_run:
            mode = "BLOCKED-MAINNET"
        eq = f"{equity:.4f}" if equity is not None else "n/a"
        print(
            f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] "
            f"{env_label()} | {mode} | equity={eq} | "
            f"{self.settings.category} {','.join(self.settings.symbols)} | "
            f"tf={self.settings.interval}m poll={self.settings.poll_seconds}s"
        )

    def tick(self) -> bool:
        """Run one evaluation cycle. Returns False if agent should stop."""
        if not self.settings.enabled:
            print("AGENT_ENABLED=false — stopping.")
            return False

        equity = get_equity(self.session)
        self.risk.update_equity(equity)
        self._status_line(equity)

        if self.risk.state.halted:
            print("KILL SWITCH:", self.risk.state.halt_reason)
            self.journal.write(
                "halt",
                reason=self.risk.state.halt_reason,
                equity="" if equity is None else f"{equity:.8f}",
                dry_run=self.settings.dry_run,
            )
            return False

        positions: dict[str, dict | None] = {}
        for symbol in self.settings.symbols:
            positions[symbol] = get_position(
                self.session,
                self.settings.category,
                symbol,
            )

        open_count = self.risk.open_position_count(positions)

        for symbol in self.settings.symbols:
            try:
                candles = fetch_candles(
                    self.session,
                    self.settings.category,
                    symbol,
                    self.settings.interval,
                    self.settings.candle_limit,
                )
            except Exception as exc:
                print(f"[{symbol}] candle error:", exc)
                continue

            signal = self.strategy.evaluate(candles)
            pos = positions.get(symbol)
            pos_txt = (
                f"{pos['side']} {pos['size']}" if pos else "flat"
            )
            print(
                f"[{symbol}] signal={signal.action.value} pos={pos_txt} "
                f"| {signal.reason}"
            )
            self.journal.write(
                "signal",
                symbol=symbol,
                category=self.settings.category,
                dry_run=self.settings.dry_run,
                reason=signal.reason,
                price=str(signal.price),
                equity="" if equity is None else f"{equity:.8f}",
                details=signal.action.value,
            )

            plan = self.risk.plan_trade(
                self.session,
                symbol,
                signal,
                pos,
                equity,
                open_count,
            )
            if not plan:
                continue

            ok = self.executor.execute(plan, equity)
            if ok and not plan.reduce_only:
                open_count += 1
            elif ok and plan.reduce_only:
                open_count = max(0, open_count - 1)

        return True

    def run_forever(self) -> None:
        print("=== Bybit Automated Trading Agent ===")
        print(f"Environment: {env_label()}")
        print(f"Dry-run: {self.settings.dry_run}")
        if is_live_mainnet():
            print("WARNING: Bybit env is MAINNET.")
            if not self.settings.allow_live:
                print(
                    "Live agent orders on mainnet are blocked "
                    "unless AGENT_ALLOW_LIVE=true."
                )
        print(f"Journal: {self.journal.path}")
        print("Ctrl+C to stop.\n")

        self.journal.write(
            "start",
            category=self.settings.category,
            dry_run=self.settings.dry_run,
            reason="agent started",
            details=",".join(self.settings.symbols),
        )

        try:
            while True:
                if not self.tick():
                    break
                time.sleep(self.settings.poll_seconds)
        except KeyboardInterrupt:
            print("\nAgent stopped by user.")
            self.journal.write(
                "stop",
                dry_run=self.settings.dry_run,
                reason="keyboard interrupt",
            )
