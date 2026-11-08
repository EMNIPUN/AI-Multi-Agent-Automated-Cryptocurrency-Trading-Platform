from __future__ import annotations

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ.setdefault(
    "SIGNAL_CLOUD_OWNER_USER_ID", "2eefcbf0-81ab-43c4-9454-67c0c53f834b"
)
os.environ["SUPABASE_SOT_ENABLED"] = "true"

from apps.api.app.config import clear_settings_cache

clear_settings_cache()

from agent.paper.config import PaperBrokerConfig
from agent.paper.store import PaperStore

store = PaperStore()
sid = f"ps_sot_smoke_{int(time.time())}"
sess = store.create_session(
    config=PaperBrokerConfig(initial_balance=Decimal("1000")),
    now_ms=1_700_000_000_000,
    session_id=sid,
)
got = store.get_session(sess.session_id)
print("OK", sess.session_id, got.available_balance if got else None)
