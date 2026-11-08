"""Isolated ephemeral paper journal for backtests — never touches user SoT."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from agent.paper.read_store import PaperReadStore
from agent.paper.store import PaperStore


BACKTEST_JOURNAL_PREFIX = "bt68a_"


def ensure_offline_sot() -> None:
    """Force offline SQLite engines for backtest persistence (no remote SoT writes)."""
    os.environ["SUPABASE_SOT_ENABLED"] = "false"
    try:
        from apps.api.app.config import clear_settings_cache

        clear_settings_cache()
    except Exception:  # noqa: BLE001
        pass


def isolated_journal_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path("data") / "backtests"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{BACKTEST_JOURNAL_PREFIX}{uuid.uuid4().hex[:12]}.sqlite3"


def open_isolated_paper_store(journal_path: str | Path) -> PaperStore:
    ensure_offline_sot()
    path = Path(journal_path)
    if path.exists():
        path.unlink()
    # Guard: never open default user journal paths for backtests.
    name = path.name.lower()
    if "cryptonova_paper.sqlite3" in name and BACKTEST_JOURNAL_PREFIX not in name:
        raise RuntimeError("refusing to use primary paper journal for backtest isolation")
    return PaperStore(path)


def open_isolated_read_store(journal_path: str | Path) -> PaperReadStore:
    ensure_offline_sot()
    return PaperReadStore(journal_path)
