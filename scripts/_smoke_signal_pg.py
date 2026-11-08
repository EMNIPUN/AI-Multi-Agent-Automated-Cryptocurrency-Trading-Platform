from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ.setdefault(
    "SIGNAL_CLOUD_OWNER_USER_ID", "2eefcbf0-81ab-43c4-9454-67c0c53f834b"
)
os.environ["SUPABASE_SOT_ENABLED"] = "true"
os.environ["SIGNAL_SUPABASE_WRITES_ENABLED"] = "true"
os.environ["SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED"] = "true"

from apps.api.app.config import clear_settings_cache

clear_settings_cache()

from agent.multi_agent.signal_history_store import SignalHistoryStore

store = SignalHistoryStore()
print("schema", store.schema_version())
risk = store.load_risk_state()
print("risk_day", risk.day_key, "halted", risk.halted)
print("OK_signal_store")
