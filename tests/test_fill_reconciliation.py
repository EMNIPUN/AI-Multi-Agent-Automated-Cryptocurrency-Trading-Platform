"""Phase 1E offline tests — evidence-based fill reconciliation (no Bybit network)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.executor import OrderExecutor
from agent.intent_store import ExecutionRow, IntentStore, IntentStoreError
from agent.journal import TradeJournal
from agent.market_data import PositionSnapshot, PositionStatus
from agent.order_intent import OrderIntentState, merge_reconcile_state
from agent.reconcile import aggregate_executions, reconcile_intent
from agent.risk import RiskManager, TradePlan
from agent.strategies.base import Signal, SignalAction
from tests.conftest import make_settings


def _plan(**overrides) -> TradePlan:
    base = dict(
        symbol="HYPEUSDT",
        side="Buy",
        qty="1",
        reduce_only=False,
        take_profit="10",
        stop_loss="9",
        reason="test-signal",
        correlation_id="corr-1e-001",
        risk_auth_ref="risk-1e-001",
    )
    base.update(overrides)
    return TradePlan(**base)


def _executor(
    tmp_path: Path,
    *,
    category: str = "linear",
    write_session=None,
    settings=None,
) -> OrderExecutor:
    settings = settings or make_settings(
        dry_run=False, allow_live=False, category=category
    )
    session = MagicMock()
    journal = TradeJournal(log_dir=tmp_path / "logs")
    store = IntentStore(db_path=tmp_path / "intents.sqlite3")
    return OrderExecutor(
        session,
        settings,
        journal,
        store=store,
        write_session=write_session or MagicMock(),
        db_path=tmp_path / "intents.sqlite3",
    )


def _seed_unresolved(
    ex: OrderExecutor, *, correlation_id: str, state: OrderIntentState
) -> object:
    intent = ex.build_intent(_plan(correlation_id=correlation_id), dry_run=False)
    ex.store.insert_created(intent)
    claimed = ex.store.try_claim_for_submission(intent.intent_id)
    assert claimed is not None
    if state is OrderIntentState.ACCEPTED:
        ex.store.transition(claimed.intent_id, OrderIntentState.ACCEPTED, exchange_order_id="OID-A")
    elif state is OrderIntentState.RECONCILIATION_REQUIRED:
        ex.store.transition(claimed.intent_id, OrderIntentState.UNKNOWN, last_error="t")
        ex.store.transition(
            claimed.intent_id,
            OrderIntentState.RECONCILIATION_REQUIRED,
            last_error="r",
        )
    elif state is OrderIntentState.PARTIALLY_FILLED:
        ex.store.transition(claimed.intent_id, OrderIntentState.ACCEPTED, exchange_order_id="OID-P")
        ex.store.transition(
            claimed.intent_id,
            OrderIntentState.PARTIALLY_FILLED,
            filled_qty="0.3",
        )
    else:
        ex.store.transition(claimed.intent_id, state, last_error="seed")
    return ex.store.get_by_intent_id(intent.intent_id)


def _ok_list(rows: list[dict], *, cursor: str = "") -> dict:
    result: dict = {"list": rows}
    if cursor:
        result["nextPageCursor"] = cursor
    return {"retCode": 0, "result": result}


def _empty_session() -> MagicMock:
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.return_value = _ok_list([])
    session.get_executions.return_value = _ok_list([])
    return session


# --- 1. Accepted without fills ---


def test_accepted_order_without_fills(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(ex, correlation_id="corr-acc-nofill", state=OrderIntentState.ACCEPTED)
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-A",
                "orderStatus": "New",
                "cumExecQty": "0",
                "leavesQty": "1",
            }
        ]
    )
    session.get_order_history.return_value = _ok_list([])
    session.get_executions.return_value = _ok_list([])
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is True
    assert result.intent.state is OrderIntentState.ACCEPTED
    assert result.intent.filled_qty in {"", "0"}


# --- 2. Single completed fill ---


def test_single_completed_fill(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(ex, correlation_id="corr-single-fill", state=OrderIntentState.ACCEPTED)
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-F",
                "orderStatus": "Filled",
                "cumExecQty": "1",
                "avgPrice": "10.5",
                "cumExecFee": "0.01",
                "leavesQty": "0",
            }
        ]
    )
    session.get_executions.return_value = _ok_list(
        [
            {
                "execId": "EX-1",
                "orderId": "OID-F",
                "orderLinkId": current.client_order_id,
                "execQty": "1",
                "execPrice": "10.5",
                "execFee": "0.01",
                "execTime": "1000",
                "leavesQty": "0",
            }
        ]
    )
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is True
    assert result.intent.state is OrderIntentState.FILLED
    assert result.intent.filled_qty == "1"
    assert result.intent.avg_exec_price == "10.5"
    assert len(ex.store.list_executions(current.intent_id)) == 1


# --- 3. Multiple partial fills ---


def test_multiple_partial_fills(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(ex, correlation_id="corr-multi-partial", state=OrderIntentState.ACCEPTED)
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-M",
                "orderStatus": "PartiallyFilled",
                "cumExecQty": "0.7",
                "leavesQty": "0.3",
            }
        ]
    )
    session.get_order_history.return_value = _ok_list([])
    session.get_executions.return_value = _ok_list(
        [
            {
                "execId": "EX-A",
                "orderLinkId": current.client_order_id,
                "orderId": "OID-M",
                "execQty": "0.4",
                "execPrice": "10",
                "execFee": "0.001",
                "execTime": "1",
            },
            {
                "execId": "EX-B",
                "orderLinkId": current.client_order_id,
                "orderId": "OID-M",
                "execQty": "0.3",
                "execPrice": "11",
                "execFee": "0.001",
                "execTime": "2",
            },
        ]
    )
    result = reconcile_intent(session, ex.store, current)
    assert result.intent.state is OrderIntentState.PARTIALLY_FILLED
    assert result.intent.filled_qty == "0.7"
    assert len(ex.store.list_executions(current.intent_id)) == 2


# --- 4. Duplicate execution event ---


def test_duplicate_execution_event_no_double_count(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(ex, correlation_id="corr-dup-exec", state=OrderIntentState.ACCEPTED)
    exec_row = {
        "execId": "EX-DUP",
        "orderLinkId": current.client_order_id,
        "orderId": "OID-D",
        "execQty": "0.5",
        "execPrice": "10",
        "execFee": "0.01",
        "execTime": "1",
    }
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-D",
                "orderStatus": "PartiallyFilled",
                "cumExecQty": "0.5",
                "leavesQty": "0.5",
            }
        ]
    )
    session.get_order_history.return_value = _ok_list([])
    session.get_executions.return_value = _ok_list([exec_row, exec_row])
    result = reconcile_intent(session, ex.store, current)
    assert result.intent.filled_qty == "0.5"
    assert len(ex.store.list_executions(current.intent_id)) == 1
    # Second reconcile with same exec must remain idempotent
    result2 = reconcile_intent(session, ex.store, result.intent)
    assert result2.intent.filled_qty == "0.5"
    assert len(ex.store.list_executions(current.intent_id)) == 1


# --- 5. Out-of-order updates ---


def test_out_of_order_updates_cannot_regress_terminal(tmp_path: Path) -> None:
    assert (
        merge_reconcile_state(OrderIntentState.FILLED, OrderIntentState.ACCEPTED)
        is OrderIntentState.FILLED
    )
    ex = _executor(tmp_path)
    current = _seed_unresolved(ex, correlation_id="corr-ooo", state=OrderIntentState.ACCEPTED)
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-O",
                "orderStatus": "Filled",
                "cumExecQty": "1",
                "leavesQty": "0",
            }
        ]
    )
    session.get_executions.return_value = _ok_list(
        [
            {
                "execId": "EX-O",
                "orderLinkId": current.client_order_id,
                "orderId": "OID-O",
                "execQty": "1",
                "execPrice": "9",
                "execFee": "0",
                "execTime": "9",
            }
        ]
    )
    filled = reconcile_intent(session, ex.store, current).intent
    assert filled.state is OrderIntentState.FILLED
    # Late "New" open-order echo must not regress
    session.get_open_orders.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-O",
                "orderStatus": "New",
                "cumExecQty": "0",
                "leavesQty": "1",
            }
        ]
    )
    session.get_order_history.return_value = _ok_list([])
    again = reconcile_intent(session, ex.store, filled)
    assert again.intent.state is OrderIntentState.FILLED


# --- 6. Partial fill then cancellation ---


def test_partial_fill_then_cancellation_preserves_qty(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-pfc", state=OrderIntentState.PARTIALLY_FILLED
    )
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-PFC",
                "orderStatus": "PartiallyFilledCanceled",
                "cumExecQty": "0.4",
                "leavesQty": "0",
            }
        ]
    )
    session.get_executions.return_value = _ok_list(
        [
            {
                "execId": "EX-PFC",
                "orderLinkId": current.client_order_id,
                "orderId": "OID-PFC",
                "execQty": "0.4",
                "execPrice": "12",
                "execFee": "0.002",
                "execTime": "5",
            }
        ]
    )
    result = reconcile_intent(session, ex.store, current)
    assert result.intent.state is OrderIntentState.CANCELED
    assert result.intent.filled_qty == "0.4"


# --- 7. Rejected with zero fills ---


def test_rejected_order_zero_fills(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-rej", state=OrderIntentState.RECONCILIATION_REQUIRED
    )
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-R",
                "orderStatus": "Rejected",
                "cumExecQty": "0",
                "leavesQty": "0",
            }
        ]
    )
    session.get_executions.return_value = _ok_list([])
    result = reconcile_intent(session, ex.store, current)
    assert result.intent.state is OrderIntentState.REJECTED
    assert result.intent.filled_qty in {"", "0"}


# --- 8. Missing in realtime, found in history ---


def test_missing_realtime_found_in_history(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-hist", state=OrderIntentState.RECONCILIATION_REQUIRED
    )
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-H",
                "orderStatus": "Filled",
                "cumExecQty": "1",
                "leavesQty": "0",
            }
        ]
    )
    session.get_executions.return_value = _ok_list([])
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is True
    assert result.intent.state is OrderIntentState.FILLED


# --- 9. Executions without complete order record ---


def test_executions_without_complete_order_record(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-exec-only", state=OrderIntentState.RECONCILIATION_REQUIRED
    )
    session = _empty_session()
    session.get_executions.return_value = _ok_list(
        [
            {
                "execId": "EX-ONLY",
                "orderLinkId": current.client_order_id,
                "orderId": "OID-E",
                "execQty": "0.2",
                "execPrice": "8",
                "execFee": "0.001",
                "execTime": "3",
                "leavesQty": "0.8",
            }
        ]
    )
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is True
    assert result.intent.state is OrderIntentState.PARTIALLY_FILLED
    assert result.intent.filled_qty == "0.2"
    assert result.intent.state is not OrderIntentState.FILLED


# --- 10. No records (inconclusive) ---


def test_no_records_inconclusive(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-none", state=OrderIntentState.RECONCILIATION_REQUIRED
    )
    result = reconcile_intent(_empty_session(), ex.store, current)
    assert result.proven is False
    assert result.intent.state in {
        OrderIntentState.RECONCILIATION_REQUIRED,
        OrderIntentState.UNKNOWN,
    }
    assert "inconclusive" in result.detail


# --- 11. Network timeout and API errors ---


def test_network_timeout_and_api_errors(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-net", state=OrderIntentState.RECONCILIATION_REQUIRED
    )
    session = MagicMock()
    session.get_open_orders.side_effect = TimeoutError("boom")
    session.get_order_history.side_effect = OSError("net")
    session.get_executions.return_value = {"retCode": 10006, "retMsg": "too many visits"}
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is False
    assert result.intent.state is OrderIntentState.UNKNOWN


# --- 12. Malformed / inconsistent responses ---


def test_malformed_and_inconsistent_responses(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-mal", state=OrderIntentState.RECONCILIATION_REQUIRED
    )
    session = MagicMock()
    session.get_open_orders.return_value = "not-a-dict"
    session.get_order_history.return_value = {"retCode": 0, "result": {"list": "bad"}}
    session.get_executions.return_value = {"result": {"list": []}}  # missing retCode
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is False
    assert result.intent.state is OrderIntentState.UNKNOWN


# --- 13. Pagination and delayed history ---


def test_pagination_and_delayed_history(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-page", state=OrderIntentState.ACCEPTED
    )
    link = current.client_order_id

    def hist(**kwargs):
        cursor = kwargs.get("cursor")
        if not cursor:
            return _ok_list(
                [],
                cursor="page2",
            )
        return _ok_list(
            [
                {
                    "orderLinkId": link,
                    "orderId": "OID-PG",
                    "orderStatus": "Filled",
                    "cumExecQty": "1",
                    "leavesQty": "0",
                }
            ]
        )

    def execs(**kwargs):
        cursor = kwargs.get("cursor")
        if not cursor:
            return _ok_list(
                [
                    {
                        "execId": "EX-P1",
                        "orderLinkId": link,
                        "orderId": "OID-PG",
                        "execQty": "0.6",
                        "execPrice": "10",
                        "execFee": "0.001",
                        "execTime": "1",
                    }
                ],
                cursor="epage2",
            )
        return _ok_list(
            [
                {
                    "execId": "EX-P2",
                    "orderLinkId": link,
                    "orderId": "OID-PG",
                    "execQty": "0.4",
                    "execPrice": "10",
                    "execFee": "0.001",
                    "execTime": "2",
                }
            ]
        )

    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.side_effect = hist
    session.get_executions.side_effect = execs
    result = reconcile_intent(session, ex.store, current)
    assert result.intent.state is OrderIntentState.FILLED
    assert result.intent.filled_qty == "1"
    assert len(ex.store.list_executions(current.intent_id)) == 2


# --- 14. Restart with accepted / unresolved ---


def test_restart_accepted_and_unresolved_recovery(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    accepted = _seed_unresolved(ex, correlation_id="corr-rs-acc", state=OrderIntentState.ACCEPTED)
    pending = ex.build_intent(_plan(correlation_id="corr-rs-pend"), dry_run=False)
    ex.store.insert_created(pending)
    ex.store.try_claim_for_submission(pending.intent_id)

    recovered = ex.recover_unresolved_on_startup()
    assert any(i.state is OrderIntentState.RECONCILIATION_REQUIRED for i in recovered)
    still = ex.store.get_by_intent_id(accepted.intent_id)
    assert still is not None
    assert still.state is OrderIntentState.ACCEPTED
    needs = ex.store.list_needs_reconcile(ex.env_scope, ex.account_fp)
    assert any(i.intent_id == accepted.intent_id for i in needs)


# --- 15. Transaction rollback / SQLite conflict ---


def test_transaction_rollback_and_sqlite_conflict(tmp_path: Path) -> None:
    store = IntentStore(db_path=tmp_path / "shared.sqlite3")
    ex = _executor(tmp_path / "ex")
    intent = ex.build_intent(_plan(correlation_id="corr-rb"), dry_run=False)
    ex.store = store
    store.insert_created(intent)
    claimed = store.try_claim_for_submission(intent.intent_id)
    store.transition(claimed.intent_id, OrderIntentState.ACCEPTED, exchange_order_id="OID")

    # Unique client_order_id conflict on insert
    ok, existing = store.insert_created(intent)
    assert ok is False
    assert existing.intent_id == intent.intent_id

    # Force rollback path via apply_reconcile_update with missing intent
    with pytest.raises(KeyError):
        store.apply_reconcile_update(
            "missing-intent",
            proposed_state=OrderIntentState.FILLED,
            executions=[],
        )
    # Original row intact
    row = store.get_by_intent_id(intent.intent_id)
    assert row is not None
    assert row.state is OrderIntentState.ACCEPTED


# --- 16. Spot vs linear quantity semantics ---


def test_spot_versus_linear_quantity_semantics(tmp_path: Path) -> None:
    # Linear contracts often use coin qty; spot may use base coin — both stored as strings.
    linear = aggregate_executions(
        [
            ExecutionRow(exec_id="L1", exec_qty="0.001", exec_price="60000", exec_fee="0.01"),
            ExecutionRow(exec_id="L2", exec_qty="0.002", exec_price="60100", exec_fee="0.02"),
        ]
    )
    spot = aggregate_executions(
        [
            ExecutionRow(exec_id="S1", exec_qty="10.5", exec_price="0.00001234", exec_fee="0.0001"),
        ]
    )
    assert linear.filled_qty == "0.003"
    assert "600" in linear.avg_exec_price or linear.avg_exec_price.startswith("600")
    assert spot.filled_qty == "10.5"
    assert spot.avg_exec_price == "0.00001234"

    ex = _executor(tmp_path, category="spot")
    current = _seed_unresolved(ex, correlation_id="corr-spot", state=OrderIntentState.ACCEPTED)
    # Override category on stored intent path via rebuild — intent already has category from settings
    session = MagicMock()
    session.get_open_orders.return_value = _ok_list([])
    session.get_order_history.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID-S",
                "orderStatus": "Filled",
                "cumExecQty": "10.5",
                "leavesQty": "0",
            }
        ]
    )
    session.get_executions.return_value = _ok_list(
        [
            {
                "execId": "EX-S",
                "orderLinkId": current.client_order_id,
                "orderId": "OID-S",
                "execQty": "10.5",
                "execPrice": "0.00001234",
                "execFee": "0.0001",
                "feeCurrency": "USDT",
                "execTime": "9",
            }
        ]
    )
    result = reconcile_intent(session, ex.store, current)
    assert result.intent.filled_qty == "10.5"
    assert result.intent.avg_exec_price == "0.00001234"


# --- 17. Phase 1A UNKNOWN position protection ---


def test_phase_1a_unknown_position_still_blocks(tmp_path: Path) -> None:
    risk = RiskManager(make_settings(), db_path=tmp_path / "risk.sqlite3")
    risk.update_equity(1000.0)
    snap = PositionSnapshot(status=PositionStatus.UNKNOWN, reason="timeout")
    plan = risk.plan_trade(
        MagicMock(),
        "HYPEUSDT",
        Signal(action=SignalAction.BUY, reason="x", price=10.0),
        snap,
        1000.0,
        0,
    )
    assert plan is None


# --- 18. Phase 1B idempotency / no blind retries ---


def test_phase_1b_idempotency_no_blind_retry(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.side_effect = TimeoutError("ambiguous")
    ex = _executor(tmp_path, write_session=write)
    plan = _plan(correlation_id="corr-1b-noretry")
    with patch("agent.executor.live_orders_blocked", return_value=None):
        ex.execute(plan, 1.0)
        ex.execute(plan, 1.0)
        other = _plan(correlation_id="corr-1b-other", reason="different")
        assert ex.execute(other, 1.0) is False
    assert write.place_order.call_count == 1


# --- 19. Phase 1C durable halt ---


def test_phase_1c_durable_halt_not_reset_by_reconcile(tmp_path: Path) -> None:
    from agent.risk_modes import AccountRiskMode

    db = tmp_path / "risk_halt.sqlite3"
    settings = make_settings()
    risk = RiskManager(settings, db_path=db)
    risk.update_equity(10_000.0)
    risk.update_equity(9_500.0)  # breach daily loss → HALTED
    assert risk.state.halted is True
    assert risk.state.mode is AccountRiskMode.HALTED

    ex = _executor(tmp_path / "intent")
    current = _seed_unresolved(
        ex, correlation_id="corr-1c-halt", state=OrderIntentState.RECONCILIATION_REQUIRED
    )
    reconcile_intent(_empty_session(), ex.store, current)
    # Re-load risk — halt must remain (reconcile does not touch risk store / auto-clear).
    risk2 = RiskManager(settings, db_path=db)
    assert risk2.state.halted is True
    assert risk2.state.mode is AccountRiskMode.HALTED


# --- 20. Phase 1D confirmed candle / signal dedupe ---


def test_phase_1d_confirmed_candle_signal_dedupe_still_imported() -> None:
    from agent.confirmed_candles import filter_confirmed_candles
    from agent.signal_ids import build_signal_id

    # Smoke: modules remain importable / callable (full coverage in test_confirmed_candles).
    assert callable(filter_confirmed_candles)
    assert callable(build_signal_id)


# --- 21. Dry-run and allow-live defaults ---


def test_dry_run_and_allow_live_defaults(tmp_path: Path) -> None:
    settings = make_settings()
    assert settings.dry_run is True
    assert settings.allow_live is False

    write = MagicMock()
    ex = _executor(
        tmp_path,
        write_session=write,
        settings=make_settings(dry_run=True, allow_live=False),
    )
    assert ex.execute(_plan(correlation_id="corr-dry"), 1.0) is True
    write.place_order.assert_not_called()


# --- 22 helpers: schema migration + blocking partial + store error ---


def test_schema_migration_preserves_existing_rows(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE order_intents (
            intent_id TEXT PRIMARY KEY,
            client_order_id TEXT NOT NULL,
            env_scope TEXT NOT NULL,
            account_fp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            category TEXT NOT NULL,
            side TEXT NOT NULL,
            qty TEXT NOT NULL,
            reduce_only INTEGER NOT NULL,
            order_type TEXT NOT NULL,
            time_in_force TEXT NOT NULL,
            take_profit TEXT,
            stop_loss TEXT,
            correlation_id TEXT NOT NULL,
            risk_auth_ref TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            dry_run INTEGER NOT NULL,
            exchange_order_id TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            filled_qty TEXT NOT NULL DEFAULT '',
            submission_attempted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE (env_scope, account_fp, client_order_id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO order_intents VALUES (
            'id1','link1','testnet','fp','HYPEUSDT','linear','Buy','1',0,
            'Market','IOC',NULL,NULL,'c','r','ACCEPTED','t','t',0,'OID','', '',0,'t'
        )
        """
    )
    conn.commit()
    conn.close()

    store = IntentStore(db_path=db)
    row = store.get_by_intent_id("id1")
    assert row is not None
    assert row.state is OrderIntentState.ACCEPTED
    assert row.remaining_qty == ""
    # New table exists
    conn = sqlite3.connect(str(db))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "order_executions" in tables
    assert "schema_meta" in tables


def test_partial_blocks_new_exposure(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.return_value = {"retCode": 0, "result": {"orderId": "X"}}
    ex = _executor(tmp_path, write_session=write)
    _seed_unresolved(ex, correlation_id="corr-block-partial", state=OrderIntentState.PARTIALLY_FILLED)
    blocking = ex.has_blocking_unresolved()
    assert blocking
    with patch("agent.executor.live_orders_blocked", return_value=None):
        assert ex.execute(_plan(correlation_id="corr-new-after-partial"), 1.0) is False
    write.place_order.assert_not_called()


def test_reconcile_store_error_surfaces(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    current = _seed_unresolved(
        ex, correlation_id="corr-store-err", state=OrderIntentState.ACCEPTED
    )
    session = _empty_session()
    session.get_order_history.return_value = _ok_list(
        [
            {
                "orderLinkId": current.client_order_id,
                "orderId": "OID",
                "orderStatus": "Filled",
                "cumExecQty": "1",
                "leavesQty": "0",
            }
        ]
    )
    with patch.object(
        ex.store, "apply_reconcile_update", side_effect=IntentStoreError("disk full")
    ):
        result = reconcile_intent(session, ex.store, current)
    assert result.store_error is True
    assert result.proven is False
