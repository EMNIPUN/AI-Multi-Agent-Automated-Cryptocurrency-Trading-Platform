"""Integration tests: synthetic signal → paper lifecycle; safety invariants."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from agent.paper.broker import PaperBroker
from agent.paper.config import PaperBrokerConfig
from agent.paper.integration import (
    PAPER_BROKER_AUTO_ATTACH,
    decision_to_paper_signal,
    submit_decision_to_paper,
)
from agent.paper.models import PaperCandle
from agent.paper.store import PaperStore


def test_auto_attach_remains_off() -> None:
    assert PAPER_BROKER_AUTO_ATTACH is False


def test_decision_mapping_and_lifecycle(tmp_path: Path) -> None:
    decision = SimpleNamespace(
        decision_id="dec_1",
        action=SimpleNamespace(value="BUY"),
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        timestamp_ms=1_000_000,
        risk=SimpleNamespace(
            verdict=SimpleNamespace(value="APPROVED"),
            position_notional=100.0,
        ),
        levels=SimpleNamespace(
            entry=100.0,
            stop_loss=95.0,
            take_profit=110.0,
        ),
        market=SimpleNamespace(newest_close_ms=1_000_000),
    )
    signal = decision_to_paper_signal(decision)
    assert signal is not None
    assert signal.action == "BUY"
    assert signal.stop_loss == Decimal("95")

    store = PaperStore(tmp_path / "paper.sqlite3")
    broker = PaperBroker(
        store,
        PaperBrokerConfig(
            initial_balance=Decimal("1000"),
            fee_rate=Decimal("0.001"),
            slippage_bps=Decimal("5"),
        ),
    )
    sess = broker.create_session(now_ms=1)
    r = submit_decision_to_paper(broker, session_id=sess.session_id, decision=decision)
    assert r.ok and r.reason == "ORDER_PENDING"

    broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=2_000_000,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    assert len(broker.store.get_open_positions(sess.session_id)) == 1

    outs = broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=3_000_000,
            open=Decimal("108"),
            high=Decimal("111"),
            low=Decimal("107"),
            close=Decimal("110"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    assert any("TAKE_PROFIT" in o.reason for o in outs)
    final = broker.get_session(sess.session_id)
    assert final is not None
    assert final.reserved_capital == Decimal("0")
    assert final.available_balance != Decimal("1000")  # fees/pnl applied


def test_missing_fields_rejected() -> None:
    bad = SimpleNamespace(decision_id=None)
    assert decision_to_paper_signal(bad) is None


def test_no_cloud_writes_in_paper_modules() -> None:
    """
    Detect real cloud/live write surfaces in paper modules.

    ``supabase_sot_enabled`` is a read-only offline/Postgres feature gate and
    does not initialize a Supabase client or perform remote writes. Docstring
    mentions of the SoT architecture are allowed. Actual Supabase/OpenAI
    clients and private order helpers remain forbidden.
    """
    import re

    root = Path(__file__).resolve().parents[1] / "agent" / "paper"
    forbidden = [
        r"create_client\s*\(",
        r"from supabase import",
        r"(?<!\.)import supabase\b",
        r"from openai",
        r"import openai",
        r"\bplace_order\b",
        r"bybit_private",
    ]
    # Code identifiers containing 'supabase' (ignore comments / docstrings).
    ident_re = re.compile(r"\bsupabase\w*\b", re.IGNORECASE)

    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for pat in forbidden:
            assert re.search(pat, lower) is None, f"{path.name} matched {pat}"

        code_only = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", text)
        code_only = re.sub(r"#.*", "", code_only)
        for match in ident_re.finditer(code_only):
            token = match.group(0).lower()
            assert token == "supabase_sot_enabled", (
                f"{path.name} contains unexpected code token {match.group(0)!r}"
            )


def test_sell_closes_long_does_not_short(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "paper.sqlite3")
    broker = PaperBroker(store, PaperBrokerConfig())
    sess = broker.create_session(now_ms=1)

    buy = SimpleNamespace(
        decision_id="buy1",
        action=SimpleNamespace(value="BUY"),
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        timestamp_ms=1000,
        risk=SimpleNamespace(
            verdict=SimpleNamespace(value="APPROVED"),
            position_notional=100.0,
        ),
        levels=SimpleNamespace(entry=100.0, stop_loss=90.0, take_profit=130.0),
        market=SimpleNamespace(newest_close_ms=1000),
    )
    submit_decision_to_paper(broker, session_id=sess.session_id, decision=buy)
    broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=2000,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )

    sell = SimpleNamespace(
        decision_id="sell1",
        action=SimpleNamespace(value="SELL"),
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        timestamp_ms=3000,
        risk=SimpleNamespace(
            verdict=SimpleNamespace(value="APPROVED"),
            position_notional=100.0,
        ),
        levels=SimpleNamespace(entry=105.0, stop_loss=None, take_profit=None),
        market=SimpleNamespace(newest_close_ms=3000),
    )
    r = submit_decision_to_paper(broker, session_id=sess.session_id, decision=sell)
    assert r.ok and r.reason == "EXIT_ORDER_PENDING"
    broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=4000,
            open=Decimal("105"),
            high=Decimal("106"),
            low=Decimal("104"),
            close=Decimal("105"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    assert broker.store.get_open_positions(sess.session_id) == []

    # Second SELL with no long → reject, not short
    sell2 = SimpleNamespace(
        decision_id="sell2",
        action=SimpleNamespace(value="SELL"),
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        timestamp_ms=5000,
        risk=SimpleNamespace(
            verdict=SimpleNamespace(value="APPROVED"),
            position_notional=100.0,
        ),
        levels=SimpleNamespace(entry=105.0, stop_loss=None, take_profit=None),
        market=SimpleNamespace(newest_close_ms=5000),
    )
    r2 = submit_decision_to_paper(broker, session_id=sess.session_id, decision=sell2)
    assert r2.reason == "NO_OPEN_LONG"
