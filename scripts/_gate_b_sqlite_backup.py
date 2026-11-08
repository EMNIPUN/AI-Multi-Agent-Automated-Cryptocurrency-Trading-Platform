"""Create WAL-safe SQLite backup for Gate B. Does not touch cloud."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.app.database_url import inspect_database_url  # noqa: E402
from scripts.verify_dev_database_target import extract_project_ref  # noqa: E402

EXPECTED_SHA = "1ea22dc805ff5bb235fec970cec1dd9b120c0daab573b210256d50856c722145"


def counts(path: Path) -> dict:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        ver = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()["value"]
        ik = conn.execute("PRAGMA integrity_check").fetchone()[0]
        out: dict = {"schema_version": ver, "integrity": ik}
        for tname in (
            "signal_history",
            "paper_risk_state",
            "evaluation_checkpoints",
            "scheduler_lock",
            "scheduler_audit",
            "cloud_sync_outbox",
        ):
            try:
                out[tname] = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
            except sqlite3.Error:
                out[tname] = None
        return out
    finally:
        conn.close()


def main() -> int:
    mig = ROOT / (
        "apps/api/alembic/versions_proposed/"
        "20261107_0004_phase4d_signal_persistence.py"
    )
    digest = hashlib.sha256(mig.read_bytes()).hexdigest()
    print("checksum", digest)
    print("checksum_match", digest == EXPECTED_SHA)
    print(
        "in_active",
        (ROOT / "apps/api/alembic/versions" / mig.name).exists(),
    )
    text = (ROOT / ".env").read_text(encoding="utf-8", errors="replace")
    keys = [
        "SIGNAL_SUPABASE_WRITES_ENABLED",
        "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED",
        "SIGNAL_CLOUD_SYNC_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED",
        "AGENT_ALLOW_LIVE",
        "TESTNET_ORDER_SUBMISSION_APPROVED",
        "PERPETUAL_AUTO_EXECUTION_ENABLED",
        "CRYPTONOVA_DEV_PROJECT_REF",
        "CRYPTONOVA_DB_TARGET",
        "CRYPTONOVA_ALLOW_DEV_MIGRATIONS",
        "SUPABASE_URL",
    ]
    for key in keys:
        m = re.search(rf"^{key}=(.*)$", text, re.M)
        val = m.group(1).strip() if m else "<unset>"
        if key == "SUPABASE_URL" and val not in ("", "<unset>"):
            try:
                val = "host=" + (urlparse(val).hostname or "unknown")
            except Exception:
                val = "set_redacted"
        print(f"{key}={val}")

    raw = ""
    for line in text.splitlines():
        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
            raw = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    print("db_host", info.host)
    print("db_project_ref", ref)
    print("db_ref_match", ref == "wmirifmgaftassgrfbyl")
    print("db_region_ap_southeast_2", "ap-southeast-2" in (info.host or ""))

    src = ROOT / "data" / "multi_agent_signals.sqlite3"
    bak_dir = ROOT / "data" / "backups"
    bak_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = bak_dir / f"multi_agent_signals_{ts}.sqlite3"
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(bak))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    print("backup_file", bak.as_posix())

    auth = counts(src)
    bak_stats = counts(bak)
    rest = bak_dir / f"_restore_check_{ts}.sqlite3"
    shutil.copy2(bak, rest)
    rest_stats = counts(rest)
    rest.unlink(missing_ok=True)
    print("auth", json.dumps(auth))
    print("backup", json.dumps(bak_stats))
    print("restore_copy", json.dumps(rest_stats))
    print("counts_match", auth == bak_stats == rest_stats)
    print(
        "backup_ok",
        bak_stats.get("integrity") == "ok" and bak_stats.get("schema_version") == "4",
    )
    return 0 if bak_stats.get("integrity") == "ok" and digest == EXPECTED_SHA else 1


if __name__ == "__main__":
    raise SystemExit(main())
