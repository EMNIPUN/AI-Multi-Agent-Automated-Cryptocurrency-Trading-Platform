"""Read-only project status snapshot for audit reports. Never prints secrets."""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    print("TOP_DIRS", sorted(p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")))
    versions = list((ROOT / "apps/api/alembic/versions").glob("*.py"))
    print("ALEMBIC_ACTIVE", sorted(v.stem for v in versions))
    prop = list((ROOT / "apps/api/alembic/versions_proposed").glob("*.py"))
    print("ALEMBIC_PROPOSED", sorted(v.stem for v in prop))

    env_text = (ROOT / ".env").read_text(encoding="utf-8", errors="replace")
    keys = [
        "APP_ENV",
        "CRYPTONOVA_DB_TARGET",
        "CRYPTONOVA_DEV_PROJECT_REF",
        "CRYPTONOVA_ALLOW_DEV_MIGRATIONS",
        "SIGNAL_SUPABASE_WRITES_ENABLED",
        "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED",
        "SIGNAL_CLOUD_SYNC_ENABLED",
        "SIGNAL_CLOUD_OWNER_USER_ID",
        "SIGNAL_AUTO_ENGINE_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED",
        "AGENT_ALLOW_LIVE",
        "AGENT_DRY_RUN",
        "PRIVATE_DATA_READS_ENABLED",
        "BYBIT_TESTNET",
        "TESTNET_ORDER_SUBMISSION_APPROVED",
        "PERPETUAL_AUTO_EXECUTION_ENABLED",
        "LLM_AGENTS_ENABLED",
        "SUPABASE_URL",
    ]
    for key in keys:
        m = re.search(rf"^{key}=(.*)$", env_text, re.M)
        val = m.group(1).strip() if m else "<unset>"
        if key == "SUPABASE_URL" and val not in ("", "<unset>"):
            try:
                val = "host=" + (urlparse(val).hostname or "unknown")
            except Exception:
                val = "set"
        print(f"ENV {key}={val}")

    raw = os.environ.get("DATABASE_URL") or ""
    info = inspect_database_url(raw)
    print("DB_HOST", info.host)
    print("DB_REF", extract_project_ref(host=info.host, user=info.user))
    print("DB_POOLER", info.pooler_hint)

    sqlite_path = ROOT / "data" / "multi_agent_signals.sqlite3"
    print("SQLITE_EXISTS", sqlite_path.exists())
    if sqlite_path.exists():
        print("SQLITE_SIZE", sqlite_path.stat().st_size)
        conn = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
        try:
            print(
                "SQLITE_SCHEMA",
                conn.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0],
            )
            print(
                "SQLITE_INTEGRITY",
                conn.execute("PRAGMA integrity_check").fetchone()[0],
            )
            for tbl in (
                "signal_history",
                "paper_risk_state",
                "cloud_sync_outbox",
                "evaluation_checkpoints",
                "scheduler_lock",
                "scheduler_audit",
            ):
                try:
                    n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    print(f"SQLITE_{tbl}", n)
                except sqlite3.Error as exc:
                    print(f"SQLITE_{tbl}", type(exc).__name__)
        finally:
            conn.close()
    bak_dir = ROOT / "data" / "backups"
    baks = sorted(bak_dir.glob("multi_agent_signals_*.sqlite3")) if bak_dir.exists() else []
    print("SQLITE_BACKUPS", [b.name for b in baks])

    url = normalize_database_url(raw, require_ssl_for_remote=True)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        rev = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        print("REMOTE_ALEMBIC", rev)
        tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='app' ORDER BY 1"
            )
        ).fetchall()
        print("REMOTE_APP_TABLES", [r[0] for r in tables])
        for tbl in (
            "signal_history",
            "signal_agent_contributions",
            "signal_risk_events",
            "scheduler_evaluation_history",
            "scheduler_audit",
        ):
            n = conn.execute(text(f'SELECT COUNT(*) FROM app."{tbl}"')).scalar()
            print(f"REMOTE_COUNT_{tbl}", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
