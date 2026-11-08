from __future__ import annotations

import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SUPABASE_SOT_ENABLED"] = "false"
from apps.api.app.config import clear_settings_cache

clear_settings_cache()

import agent.paper.broker as br
from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.models import PaperCandle
from agent.paper.store import PaperStore

orig = br.PaperBroker._close_position


def wrap(self, *a, **k):
    try:
        return orig(self, *a, **k)
    except Exception as e:
        print("EXC", type(e).__name__, e)
        raise


br.PaperBroker._close_position = wrap  # type: ignore[method-assign]

td = Path(tempfile.mkdtemp())
b = PaperBroker(
    PaperStore(td / "p.sqlite3"),
    PaperBrokerConfig(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
    ),
)
s = b.create_session(now_ms=1)
b.submit_signal(
    session_id=s.session_id,
    signal=PaperSignalInput(
        signal_id="sig1",
        symbol="BTCUSDT",
        category="spot",
        action="BUY",
        risk_verdict="APPROVED",
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("110"),
        position_notional=Decimal("100"),
        signal_candle_start_ms=1000,
        created_ms=1000,
    ),
)
b.process_candle(
    session_id=s.session_id,
    candle=PaperCandle(
        start_ms=2000,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        symbol="BTCUSDT",
        interval="15",
    ),
)
print(
    b.process_candle(
        session_id=s.session_id,
        candle=PaperCandle(
            start_ms=3000,
            open=Decimal("105"),
            high=Decimal("111"),
            low=Decimal("104"),
            close=Decimal("110.5"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
)
