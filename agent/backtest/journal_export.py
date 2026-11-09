"""Copy one isolated SQLite backtest into the Postgres journal.

The runner does not call this. It is the parity path for a local PostgreSQL
database and does not change paper balances.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent.backtest.models import BacktestResult
from agent.backtest.pg_journal import BacktestJournalUnavailable, PostgresBacktestJournal
from agent.backtest.store import open_isolated_read_store
from agent.paper.store import PaperStore


def _side(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def export_sqlite_backtest(
    journal: PostgresBacktestJournal,
    result: BacktestResult,
    *,
    owner_user_id: str,
) -> dict[str, int]:
    """Project the SQLite paper journal. A second call replays the same fill ids."""
    path = result.journal_path
    reader = open_isolated_read_store(path)
    store = PaperStore(path, isolated_sqlite=True)
    session_id = result.session_id
    orders = reader.list_orders(session_id, limit=200)
    fills = reader.list_fills(session_id, limit=200)
    if len(orders) >= 200 or len(fills) >= 200:
        raise BacktestJournalUnavailable("export_truncated")
    snapshots = reader.list_equity_snapshots(session_id, limit=500)
    closed = reader.list_closed_positions(session_id, limit=500)
    opens = store.get_open_positions(session_id)
    risk = store.get_risk_state(session_id)

    by_order: dict[str, list[Any]] = {}
    for fill in fills:
        by_order.setdefault(fill.order_id, []).append(fill)
    planned_fills: list[dict[str, object]] = []
    for order_id, group in by_order.items():
        ordered = sorted(group, key=lambda item: (item.filled_ms, item.role, item.fill_id))
        for seq, fill in enumerate(ordered, start=1):
            planned_fills.append(
                {
                    "run_id": result.run_id,
                    "owner_user_id": owner_user_id,
                    "order_id": order_id,
                    "fill_seq": seq,
                    "price": fill.price,
                    "quantity": fill.quantity,
                    "fee": fill.fee,
                    "slippage": fill.slippage,
                    "filled_at_ms": fill.filled_ms,
                }
            )

    positions: list[dict[str, object]] = []
    for position in list(opens) + list(closed):
        positions.append(
            {
                "position_id": f"{result.run_id}:{position.symbol}:{position.position_id}"[:64],
                "run_id": result.run_id,
                "owner_user_id": owner_user_id,
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_price": position.entry_price,
                "updated_at_ms": position.closed_ms or position.opened_ms,
            }
        )
    # One snapshot per symbol. Later rows in this list win inside the transaction
    # only if they share a symbol; keep the last update for each symbol.
    latest: dict[str, dict[str, object]] = {}
    for row in positions:
        current = latest.get(str(row["symbol"]))
        if current is None or int(row["updated_at_ms"]) >= int(current["updated_at_ms"]):
            latest[str(row["symbol"])] = row

    equity_rows = []
    for snap in snapshots:
        marked = snap.get("marked_equity") or snap.get("available_balance") or "0"
        equity_rows.append(
            {
                "snapshot_id": str(snap["snapshot_id"])[:64],
                "run_id": result.run_id,
                "owner_user_id": owner_user_id,
                "at_ms": int(snap["as_of_ms"]),
                "equity": marked,
                "cash": snap.get("available_balance") or "0",
            }
        )
    if not equity_rows:
        equity_rows.append(
            {
                "snapshot_id": f"{result.run_id}:final"[:64],
                "run_id": result.run_id,
                "owner_user_id": owner_user_id,
                "at_ms": int(result.created_ms),
                "equity": result.final_marked_equity,
                "cash": result.final_available_balance,
            }
        )

    journal.write_run(
        run={
            "run_id": result.run_id,
            "owner_user_id": owner_user_id,
            "symbol": str(result.effective_config.get("symbol") or "BTCUSDT"),
            "interval": str(result.effective_config.get("interval") or "15"),
            "config_json": result.effective_config,
            "dataset_hash": result.dataset.content_hash[:64],
            "result_hash": (result.result_hash or "")[:64] or None,
            "status": result.status.value,
            "created_at_ms": int(result.created_ms),
        },
        orders=[
            {
                "order_id": order.order_id,
                "run_id": result.run_id,
                "owner_user_id": owner_user_id,
                "symbol": order.symbol,
                "side": _side(order.side),
                "quantity": order.quantity,
                "status": _side(order.status) if hasattr(order.status, "value") else str(order.status),
                "idempotency_key": f"{order.source_signal_id}:{_side(order.side)}"[:128],
            }
            for order in orders
        ],
        fills=planned_fills,
        positions=list(latest.values()),
        equity=equity_rows,
        risk={
            "run_id": result.run_id,
            "owner_user_id": owner_user_id,
            "halted": bool(risk and risk.get("halted")),
            "reason": str((risk or {}).get("halt_reason") or ""),
            "updated_at_ms": int((risk or {}).get("updated_ms") or result.created_ms),
        },
    )
    fee_total = sum((Decimal(str(fill.fee)) for fill in fills), Decimal("0"))
    slip_total = sum((Decimal(str(fill.slippage)) for fill in fills), Decimal("0"))
    return {
        "orders": len(orders),
        "fills": len(fills),
        "positions": len(latest),
        "equity": len(equity_rows),
        "fee_total": fee_total,
        "slippage_total": slip_total,
    }
