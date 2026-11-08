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

from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.models import PaperCandle
from agent.paper.store import PaperStore

td = Path(tempfile.mkdtemp())
store = PaperStore(td / "p.sqlite3")
b = PaperBroker(
    store,
    PaperBrokerConfig(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
    ),
)
s = b.create_session(now_ms=1)
print("session", s.session_id)
r = b.submit_signal(
    session_id=s.session_id,
    signal=PaperSignalInput(
        signal_id="sig1",
        symbol="BTCUSDT",
        category="spot",
        action="BUY",
        risk_verdict="APPROVED",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        position_notional=Decimal("100"),
        signal_candle_start_ms=1000,
        created_ms=1000,
    ),
)
print("submit", r)
pending = store.list_pending_orders(s.session_id)
print("pending", len(pending), pending[0].order_id if pending else None)
out = b.process_candle(
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
print("candle", out)
print("open", store.get_open_positions(s.session_id))
print("orders", [o.status for o in [store.get_order(pending[0].order_id)] if pending])
