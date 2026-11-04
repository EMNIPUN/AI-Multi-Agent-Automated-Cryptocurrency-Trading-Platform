from pybit.unified_trading import HTTP

from agent.config import AgentSettings, live_orders_blocked
from agent.journal import TradeJournal
from agent.risk import TradePlan


class OrderExecutor:
    def __init__(
        self,
        session: HTTP,
        settings: AgentSettings,
        journal: TradeJournal,
    ) -> None:
        self.session = session
        self.settings = settings
        self.journal = journal

    def ensure_leverage(self, symbol: str) -> None:
        if self.settings.category != "linear":
            return
        if self.settings.dry_run:
            return
        lev = str(self.settings.leverage)
        try:
            response = self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=lev,
                sellLeverage=lev,
            )
            code = response.get("retCode")
            if code not in (0, 110043):
                print(f"[{symbol}] set leverage warning:", response.get("retMsg"))
        except Exception as exc:
            print(f"[{symbol}] set leverage failed:", exc)

    def execute(self, plan: TradePlan, equity: float | None) -> bool:
        block = live_orders_blocked(self.settings)
        dry = self.settings.dry_run or block is not None
        if block and not self.settings.dry_run:
            print(f"BLOCKED: {block}")
            self.journal.write(
                "blocked",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=True,
                reason=block,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False

        summary = (
            f"{plan.side} {plan.qty} {plan.symbol} "
            f"{'(reduceOnly) ' if plan.reduce_only else ''}"
            f"TP={plan.take_profit or '-'} SL={plan.stop_loss or '-'}"
        )

        if dry:
            print(f"[DRY-RUN] Would place: {summary} | {plan.reason}")
            self.journal.write(
                "dry_run",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=True,
                reason=plan.reason,
                equity="" if equity is None else f"{equity:.8f}",
                details=summary,
            )
            return True

        self.ensure_leverage(plan.symbol)

        params: dict = {
            "category": self.settings.category,
            "symbol": plan.symbol,
            "side": plan.side,
            "orderType": "Market",
            "qty": plan.qty,
            "timeInForce": "IOC",
        }
        if self.settings.category == "linear":
            params["positionIdx"] = 0
            if plan.reduce_only:
                params["reduceOnly"] = True
            if plan.take_profit and not plan.reduce_only:
                params["takeProfit"] = plan.take_profit
            if plan.stop_loss and not plan.reduce_only:
                params["stopLoss"] = plan.stop_loss

        try:
            response = self.session.place_order(**params)
            if response.get("retCode") != 0:
                msg = response.get("retMsg") or "order failed"
                print(f"[{plan.symbol}] order error:", msg)
                self.journal.write(
                    "error",
                    symbol=plan.symbol,
                    category=self.settings.category,
                    side=plan.side,
                    qty=plan.qty,
                    dry_run=False,
                    reason=msg,
                    equity="" if equity is None else f"{equity:.8f}",
                )
                return False

            result = response.get("result") or {}
            order_id = str(result.get("orderId") or "")
            print(f"[{plan.symbol}] ORDER OK {summary} id={order_id}")
            self.journal.write(
                "order",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=False,
                reason=plan.reason,
                order_id=order_id,
                equity="" if equity is None else f"{equity:.8f}",
                details=summary,
            )
            return True
        except Exception as exc:
            print(f"[{plan.symbol}] order exception:", exc)
            self.journal.write(
                "error",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=False,
                reason=str(exc),
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False
