"""Phase 1B offline tests — idempotent order intents (no Bybit network)."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.config import live_orders_blocked
from agent.executor import OrderExecutor
from agent.intent_store import IntentStore
from agent.journal import TradeJournal
from agent.market_data import PositionSnapshot, PositionStatus
from agent.order_ids import (
    build_client_order_id,
    intent_fingerprint,
    validate_order_link_id,
)
from agent.order_intent import OrderIntentState
from agent.reconcile import reconcile_intent
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
        correlation_id="corr-test-001",
        risk_auth_ref="risk-test-001",
    )
    base.update(overrides)
    return TradePlan(**base)


def _executor(tmp_path: Path, settings=None, write_session=None) -> OrderExecutor:
    settings = settings or make_settings(dry_run=False, allow_live=False)
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


def test_order_link_id_unique_stable_and_valid() -> None:
    fp = intent_fingerprint(
        env_scope="testnet",
        account_fp="abc",
        category="linear",
        symbol="HYPEUSDT",
        side="Buy",
        qty="1",
        reduce_only=False,
        take_profit="10",
        stop_loss="9",
        correlation_id="corr-1",
    )
    a = build_client_order_id(fp)
    b = build_client_order_id(fp)
    assert a == b
    assert validate_order_link_id(a)
    assert len(a) <= 36

    fp2 = intent_fingerprint(
        env_scope="testnet",
        account_fp="abc",
        category="linear",
        symbol="HYPEUSDT",
        side="Sell",
        qty="1",
        reduce_only=False,
        take_profit="10",
        stop_loss="9",
        correlation_id="corr-1",
    )
    assert build_client_order_id(fp2) != a


def test_repeated_processing_same_intent_no_second_submission(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.return_value = {
        "retCode": 0,
        "result": {"orderId": "OID-1", "orderLinkId": "x"},
    }
    ex = _executor(tmp_path, write_session=write)
    plan = _plan()

    with patch("agent.executor.live_orders_blocked", return_value=None):
        assert ex.execute(plan, 1000.0) is True
        assert ex.execute(plan, 1000.0) is True

    assert write.place_order.call_count == 1
    kwargs = write.place_order.call_args.kwargs
    assert "orderLinkId" in kwargs
    assert validate_order_link_id(kwargs["orderLinkId"])


def test_concurrent_duplicate_submission_attempts(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.return_value = {
        "retCode": 0,
        "result": {"orderId": "OID-C", "orderLinkId": "x"},
    }
    ex = _executor(tmp_path, write_session=write)
    plan = _plan(correlation_id="corr-concurrent")
    results: list[bool] = []

    def worker() -> None:
        with patch("agent.executor.live_orders_blocked", return_value=None):
            results.append(ex.execute(plan, 1000.0))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert write.place_order.call_count == 1
    assert results.count(True) >= 1


def test_successful_order_acknowledgement_is_accepted_not_filled(
    tmp_path: Path,
) -> None:
    write = MagicMock()
    write.place_order.return_value = {
        "retCode": 0,
        "result": {"orderId": "OID-OK"},
    }
    ex = _executor(tmp_path, write_session=write)
    with patch("agent.executor.live_orders_blocked", return_value=None):
        assert ex.execute(_plan(correlation_id="corr-ack"), 1000.0) is True
    rows = list(ex.store.list_unresolved(ex.env_scope, ex.account_fp))
    # ACCEPTED is resolved enough to not block as UNKNOWN
    intent = ex.store.get_by_client_order_id(
        ex.env_scope,
        ex.account_fp,
        ex.build_intent(_plan(correlation_id="corr-ack"), dry_run=False).client_order_id,
    )
    assert intent is not None
    assert intent.state is OrderIntentState.ACCEPTED
    assert intent.state is not OrderIntentState.FILLED


def test_api_timeout_after_possible_acceptance_no_retry(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.side_effect = TimeoutError("read timed out")
    ex = _executor(tmp_path, write_session=write)
    with patch("agent.executor.live_orders_blocked", return_value=None):
        assert ex.execute(_plan(correlation_id="corr-timeout"), 1000.0) is False
        assert ex.execute(_plan(correlation_id="corr-timeout"), 1000.0) is False
    assert write.place_order.call_count == 1
    intent = ex.store.get_by_client_order_id(
        ex.env_scope,
        ex.account_fp,
        ex.build_intent(_plan(correlation_id="corr-timeout"), dry_run=False).client_order_id,
    )
    assert intent is not None
    assert intent.state is OrderIntentState.RECONCILIATION_REQUIRED


def test_network_interruption(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.side_effect = OSError("connection reset")
    ex = _executor(tmp_path, write_session=write)
    with patch("agent.executor.live_orders_blocked", return_value=None):
        assert ex.execute(_plan(correlation_id="corr-net"), 1000.0) is False
    assert write.place_order.call_count == 1
    intent = ex.store.get_by_client_order_id(
        ex.env_scope,
        ex.account_fp,
        ex.build_intent(_plan(correlation_id="corr-net"), dry_run=False).client_order_id,
    )
    assert intent.state is OrderIntentState.RECONCILIATION_REQUIRED


def test_explicit_order_rejection(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.return_value = {"retCode": 110001, "retMsg": "order rejected"}
    ex = _executor(tmp_path, write_session=write)
    with patch("agent.executor.live_orders_blocked", return_value=None):
        assert ex.execute(_plan(correlation_id="corr-rej"), 1000.0) is False
    intent = ex.store.get_by_client_order_id(
        ex.env_scope,
        ex.account_fp,
        ex.build_intent(_plan(correlation_id="corr-rej"), dry_run=False).client_order_id,
    )
    assert intent.state is OrderIntentState.REJECTED


def test_malformed_api_response(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.return_value = ["not", "a", "dict"]
    ex = _executor(tmp_path, write_session=write)
    with patch("agent.executor.live_orders_blocked", return_value=None):
        assert ex.execute(_plan(correlation_id="corr-mal"), 1000.0) is False
    intent = ex.store.get_by_client_order_id(
        ex.env_scope,
        ex.account_fp,
        ex.build_intent(_plan(correlation_id="corr-mal"), dry_run=False).client_order_id,
    )
    assert intent.state is OrderIntentState.RECONCILIATION_REQUIRED


def test_process_restart_with_unresolved_intent(tmp_path: Path) -> None:
    db = tmp_path / "restart.sqlite3"
    store = IntentStore(db_path=db)
    settings = make_settings(dry_run=False)
    session = MagicMock()
    journal = TradeJournal(log_dir=tmp_path / "logs")
    write = MagicMock()
    ex1 = OrderExecutor(
        session, settings, journal, store=store, write_session=write, db_path=db
    )
    intent = ex1.build_intent(_plan(correlation_id="corr-restart"), dry_run=False)
    store.insert_created(intent)
    store.try_claim_for_submission(intent.intent_id)

    ex2 = OrderExecutor(
        session, settings, journal, store=store, write_session=write, db_path=db
    )
    recovered = ex2.recover_unresolved_on_startup()
    assert len(recovered) == 1
    assert recovered[0].state is OrderIntentState.RECONCILIATION_REQUIRED
    assert write.place_order.call_count == 0


def test_sqlite_uniqueness_constraint(tmp_path: Path) -> None:
    store = IntentStore(db_path=tmp_path / "uniq.sqlite3")
    settings = make_settings()
    ex = OrderExecutor(
        MagicMock(),
        settings,
        TradeJournal(log_dir=tmp_path / "logs"),
        store=store,
        write_session=MagicMock(),
    )
    intent = ex.build_intent(_plan(correlation_id="corr-uniq"), dry_run=True)
    ok1, _ = store.insert_created(intent)
    ok2, existing = store.insert_created(intent)
    assert ok1 is True
    assert ok2 is False
    assert existing.intent_id == intent.intent_id


def test_reconciliation_found_order(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    intent = ex.build_intent(_plan(correlation_id="corr-rec-found"), dry_run=False)
    ex.store.insert_created(intent)
    ex.store.try_claim_for_submission(intent.intent_id)
    ex.store.transition(
        intent.intent_id,
        OrderIntentState.UNKNOWN,
        last_error="timeout",
    )
    ex.store.transition(
        intent.intent_id,
        OrderIntentState.RECONCILIATION_REQUIRED,
        last_error="need reconcile",
    )
    current = ex.store.get_by_intent_id(intent.intent_id)
    session = MagicMock()
    session.get_open_orders.return_value = {"retCode": 0, "result": {"list": []}}
    session.get_order_history.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "orderLinkId": intent.client_order_id,
                    "orderId": "OID-R",
                    "orderStatus": "Filled",
                    "cumExecQty": "1",
                }
            ]
        },
    }
    session.get_executions.return_value = {"retCode": 0, "result": {"list": []}}
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is True
    assert result.intent.state is OrderIntentState.FILLED


def test_reconciliation_found_partial_fill(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    intent = ex.build_intent(_plan(correlation_id="corr-partial"), dry_run=False)
    ex.store.insert_created(intent)
    claimed = ex.store.try_claim_for_submission(intent.intent_id)
    ex.store.transition(claimed.intent_id, OrderIntentState.UNKNOWN, last_error="t")
    ex.store.transition(
        claimed.intent_id,
        OrderIntentState.RECONCILIATION_REQUIRED,
        last_error="r",
    )
    current = ex.store.get_by_intent_id(intent.intent_id)
    session = MagicMock()
    session.get_open_orders.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "orderLinkId": intent.client_order_id,
                    "orderId": "OID-P",
                    "orderStatus": "PartiallyFilled",
                    "cumExecQty": "0.4",
                }
            ]
        },
    }
    session.get_order_history.return_value = {"retCode": 0, "result": {"list": []}}
    session.get_executions.return_value = {"retCode": 0, "result": {"list": []}}
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is True
    assert result.intent.state is OrderIntentState.PARTIALLY_FILLED


def test_reconciliation_unable_to_establish_order_state(tmp_path: Path) -> None:
    ex = _executor(tmp_path)
    intent = ex.build_intent(_plan(correlation_id="corr-inconcl"), dry_run=False)
    ex.store.insert_created(intent)
    claimed = ex.store.try_claim_for_submission(intent.intent_id)
    ex.store.transition(claimed.intent_id, OrderIntentState.UNKNOWN, last_error="t")
    ex.store.transition(
        claimed.intent_id,
        OrderIntentState.RECONCILIATION_REQUIRED,
        last_error="r",
    )
    current = ex.store.get_by_intent_id(intent.intent_id)
    session = MagicMock()
    session.get_open_orders.return_value = {"retCode": 0, "result": {"list": []}}
    session.get_order_history.return_value = {"retCode": 0, "result": {"list": []}}
    session.get_executions.return_value = {"retCode": 0, "result": {"list": []}}
    result = reconcile_intent(session, ex.store, current)
    assert result.proven is False
    assert result.intent.state in {
        OrderIntentState.RECONCILIATION_REQUIRED,
        OrderIntentState.UNKNOWN,
    }


def test_no_automatic_retry_after_ambiguous_submission(tmp_path: Path) -> None:
    write = MagicMock()
    write.place_order.side_effect = TimeoutError("ambiguous")
    ex = _executor(tmp_path, write_session=write)
    plan = _plan(correlation_id="corr-noretry")
    with patch("agent.executor.live_orders_blocked", return_value=None):
        ex.execute(plan, 1.0)
        ex.execute(plan, 1.0)
        # Still blocked for new exposure while unresolved
        other = _plan(correlation_id="corr-other-new", reason="different")
        assert ex.execute(other, 1.0) is False
    assert write.place_order.call_count == 1


def test_phase_1a_position_unknown_still_blocks(tmp_path: Path) -> None:
    risk = RiskManager(make_settings())
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


def test_dry_run_remains_non_executing(tmp_path: Path) -> None:
    write = MagicMock()
    settings = make_settings(dry_run=True, allow_live=False)
    ex = _executor(tmp_path, settings=settings, write_session=write)
    assert ex.execute(_plan(correlation_id="corr-dry"), 1000.0) is True
    write.place_order.assert_not_called()
    intent = ex.store.get_by_client_order_id(
        ex.env_scope,
        ex.account_fp,
        ex.build_intent(_plan(correlation_id="corr-dry"), dry_run=True).client_order_id,
    )
    assert intent is not None
    assert intent.dry_run is True
    assert intent.state is OrderIntentState.CANCELED
    assert intent.state is not OrderIntentState.FILLED
    text = ex.journal.path.read_text(encoding="utf-8")
    assert "dry_run" in text
    assert "not_filled" in text


def test_live_mode_restrictions_unchanged() -> None:
    settings = make_settings(dry_run=False, allow_live=False)
    with patch("agent.config.is_live_mainnet", return_value=True):
        blocked = live_orders_blocked(settings)
    assert blocked is not None
    assert "Mainnet" in blocked

    dry = make_settings(dry_run=True, allow_live=False)
    assert dry.dry_run is True


def test_write_session_disables_force_retry() -> None:
    from bot.client import create_write_session

    with patch("bot.client.HTTP") as http_cls:
        create_write_session()
        kwargs = http_cls.call_args.kwargs
        assert kwargs["force_retry"] is False
        assert kwargs["max_retries"] == 1
