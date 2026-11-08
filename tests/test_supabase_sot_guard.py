"""Guard: core SoT stores must not import sqlite3."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_MODULES = [
    ROOT / "agent" / "multi_agent" / "signal_history_store.py",
    ROOT / "agent" / "paper" / "store.py",
    ROOT / "agent" / "paper" / "read_store.py",
    ROOT / "agent" / "intent_store.py",
    ROOT / "agent" / "risk_store.py",
    ROOT / "agent" / "signal_ledger.py",
    ROOT / "agent" / "automation" / "exec_store.py",
    ROOT / "agent" / "telemetry_ledger.py",
    ROOT / "agent" / "order_lifecycle_observer.py",
]


def test_sot_modules_have_no_sqlite3_import() -> None:
    for path in _MODULES:
        src = path.read_text(encoding="utf-8")
        assert "import sqlite3" not in src, path.name
        assert "from sqlite3" not in src, path.name


def test_supabase_sot_enabled_default_in_config_field() -> None:
    from apps.api.app.config import ApiSettings

    # Field default is True; pytest conftest forces false via env for isolation.
    field = ApiSettings.model_fields["supabase_sot_enabled"]
    assert field.default is True
