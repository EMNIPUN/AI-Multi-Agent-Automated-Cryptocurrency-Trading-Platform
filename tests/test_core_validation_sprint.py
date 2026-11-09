"""Validation sprint: smoke gates, campaign harness, reliability, testnet read-only."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from agent.multi_agent.types import DecisionAction, RiskVerdict
from agent.orchestrator.smoke import (
    APPROVAL_PHRASE,
    operator_approval_checkpoint,
    run_paid_smoke,
    run_schema_validation_smoke,
)
from agent.paper.config import PaperBrokerConfig
from agent.supervisor.campaign import CampaignConfig, PaperCampaign
from agent.supervisor.machine import PaperSupervisor
from apps.api.app.exchange.testnet_readonly import FakeTestnetReadClient, prepare_testnet_readonly
from tests.test_core_supervisor import _candle, _scripted


def test_openai_smoke_checkpoint_does_not_call_network() -> None:
    checkpoint = operator_approval_checkpoint()
    assert checkpoint["api_key_redacted"] is True
    assert checkpoint["trading_tools_in_smoke"] is False
    assert checkpoint["approval_phrase"] == APPROVAL_PHRASE
    assert "I_APPROVE" in checkpoint["instructions"]


def test_openai_schema_smoke_offline() -> None:
    result = run_schema_validation_smoke()
    assert result.ok is True
    assert result.paid_call_attempted is False
    assert result.live_orders is False
    assert result.details["disallowed_tool_rejected"] is True


def test_paid_smoke_refuses_without_approval_phrase() -> None:
    result = run_paid_smoke(approval_phrase="not-approved")
    assert result.ok is False
    assert result.paid_call_attempted is False
    assert result.openai_called is False
    assert "No paid call" in result.message


def test_paper_campaign_tracks_hold_and_blocks_without_live_orders(tmp_path: Path) -> None:
    candles = [_candle(1_000, 76.0)]

    def fetch(**_kwargs):
        return candles

    campaign = PaperCampaign(
        CampaignConfig(
            journal_path=str(tmp_path / "campaign.sqlite3"),
            report_path=str(tmp_path / "campaign.json"),
            duration_hours=48,
            poll_seconds=0,
        ),
        fetch_candles=fetch,
        evaluate=_scripted((DecisionAction.HOLD, RiskVerdict.APPROVED)),
        now_ms=lambda: 1_000,
    )
    started = campaign.start()
    assert started["mode"] == "PAPER"
    assert started["live_orders"] is False
    body = campaign.tick_once()
    assert body["counters"]["cycles"] == 1
    assert body["counters"]["hold_count"] >= 1
    assert body["exchange_order_sent"] is False
    assert body["profit_target_is_requirement"] is False
    # Not wall-clock complete after one tick.
    assert body["wall_clock_complete"] is False


def test_supervisor_stale_data_and_pause_reliability(tmp_path: Path) -> None:
    supervisor = PaperSupervisor(
        tmp_path / "sup.sqlite3",
        PaperBrokerConfig(initial_balance=Decimal("1000"), max_total_exposure=Decimal("1000")),
        evaluate=_scripted((DecisionAction.BUY, RiskVerdict.APPROVED)),
        worker_token="worker-a",
    )
    supervisor.command("start", now_ms=1_000)
    stale = supervisor.run_cycle(
        [_candle(1_000)],
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        now_ms=1_000,
        data_fresh=False,
    )
    assert stale["state"] == "ERROR"
    assert stale["block_new_exposure"] is True

    supervisor2 = PaperSupervisor(
        tmp_path / "sup2.sqlite3",
        PaperBrokerConfig(initial_balance=Decimal("1000"), max_total_exposure=Decimal("1000")),
        evaluate=_scripted(
            (DecisionAction.BUY, RiskVerdict.APPROVED),
            (DecisionAction.HOLD, RiskVerdict.APPROVED),
        ),
        worker_token="worker-a",
    )
    supervisor2.command("start", now_ms=1_000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    supervisor2.run_cycle([_candle(1_000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=1_000)
    supervisor2.command("pause", now_ms=1_500)
    paused = supervisor2.run_cycle(
        [_candle(2_000)],
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        now_ms=2_000,
    )
    assert paused["reason"] == "PAUSED_PROTECTIVE_MONITORING"
    assert paused["open_positions"] == 0


def test_restart_with_open_position_does_not_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "open.sqlite3"
    evaluate = _scripted(
        (DecisionAction.BUY, RiskVerdict.APPROVED),
        (DecisionAction.HOLD, RiskVerdict.APPROVED),
        (DecisionAction.HOLD, RiskVerdict.APPROVED),
    )
    first = PaperSupervisor(
        path,
        PaperBrokerConfig(initial_balance=Decimal("1000"), max_total_exposure=Decimal("1000")),
        evaluate=evaluate,
        worker_token="worker-a",
    )
    first.command("start", now_ms=1_000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    first.run_cycle([_candle(1_000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=1_000)
    opened = first.run_cycle([_candle(2_000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=2_000)
    assert opened["open_positions"] == 1
    session_id = first.status()["session_id"]

    second = PaperSupervisor(
        path,
        PaperBrokerConfig(initial_balance=Decimal("1000"), max_total_exposure=Decimal("1000")),
        evaluate=_scripted((DecisionAction.HOLD, RiskVerdict.APPROVED)),
        worker_token="worker-a",
    )
    assert second.status()["session_id"] == session_id
    again = second.run_cycle([_candle(2_000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=2_500)
    assert again.get("reason") == "duplicate_candle"
    assert second.report()["open_positions"] == 1


def test_testnet_readonly_prep_ok_and_auth_fail(monkeypatch) -> None:
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    ok = prepare_testnet_readonly(FakeTestnetReadClient(mode="ok"), symbol="HYPEUSDT")
    assert ok["ok"] is True
    assert ok["order_submission"] is False
    assert ok["live_orders"] is False
    assert ok["checks"]["instrument_metadata"] is True

    bad = prepare_testnet_readonly(FakeTestnetReadClient(mode="auth_fail"), symbol="HYPEUSDT")
    assert bad["ok"] is False
    assert bad["error"] == "authentication_failed"

    wrong = prepare_testnet_readonly(FakeTestnetReadClient(mode="wrong_env"), symbol="HYPEUSDT")
    assert wrong["ok"] is False
    assert wrong["error"] == "wrong_environment"
