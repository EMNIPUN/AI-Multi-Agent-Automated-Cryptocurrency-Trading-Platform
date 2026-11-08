"""Gate B0 read-only SQLite inspect + disposable backup/restore self-test. No auth DB mutation."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AUTH = ROOT / "data" / "multi_agent_signals.sqlite3"


def inspect_readonly(path: Path) -> dict:
    out: dict = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return out
    out["size_bytes"] = path.stat().st_size
    wal = Path(str(path) + "-wal")
    shm = Path(str(path) + "-shm")
    out["wal_exists"] = wal.exists()
    out["wal_size"] = wal.stat().st_size if wal.exists() else 0
    out["shm_exists"] = shm.exists()

    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        meta = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        out["schema_version"] = meta["value"] if meta else None
        for t in (
            "signal_history",
            "paper_risk_state",
            "evaluation_checkpoints",
            "scheduler_lock",
            "scheduler_audit",
            "cloud_sync_outbox",
        ):
            try:
                out[f"count_{t}"] = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()[
                    "n"
                ]
            except sqlite3.Error as exc:
                out[f"count_{t}"] = f"ERR:{type(exc).__name__}"
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM cloud_sync_outbox GROUP BY status"
            ).fetchall()
            out["outbox_by_status"] = {r["status"]: r["n"] for r in rows}
            cols = [r[1] for r in conn.execute("PRAGMA table_info(cloud_sync_outbox)")]
            out["outbox_columns"] = cols
            full = legacy = other = 0
            for r in conn.execute("SELECT payload_json FROM cloud_sync_outbox"):
                try:
                    pl = json.loads(r[0] or "{}")
                except json.JSONDecodeError:
                    pl = {}
                if pl.get("payload_schema_version"):
                    full += 1
                elif "decision" not in pl and "decision_id" in pl:
                    legacy += 1
                else:
                    other += 1
            out["outbox_full_4d"] = full
            out["outbox_legacy_summary"] = legacy
            out["outbox_other"] = other
        except sqlite3.Error as exc:
            out["outbox_scan_error"] = type(exc).__name__
        out["integrity_check"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        # Note: journal_mode on ro open may report delete; authoritative mode is from RW opens.
        out["journal_mode_ro_probe"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    return out


def disposable_backup_restore_selftest() -> dict:
    """Prove sqlite3 backup API works without touching authoritative DB."""
    from agent.multi_agent.signal_history_store import SignalHistoryStore
    from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
    from agent.multi_agent.pipeline import SignalPipeline
    from agent.multi_agent.risk_agent import SignalRiskState

    td = Path(tempfile.mkdtemp(prefix="gate_b0_sqlite_"))
    try:
        src = td / "src.sqlite3"
        bak = td / "backup.sqlite3"
        restored = td / "restored.sqlite3"
        store = SignalHistoryStore(src)
        candles = make_series(bullish_trend_closes())
        SignalPipeline(
            history_store=store, persist=True, risk_state=SignalRiskState()
        ).evaluate(
            symbol="BTCUSDT",
            category="linear",
            interval="15",
            candles=candles,
            now_ms=series_now_ms(candles),
        )
        n_src = store.list_signals(limit=10)
        # Online backup API (safe with WAL)
        src_conn = sqlite3.connect(str(src))
        try:
            dst_conn = sqlite3.connect(str(bak))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        shutil.copy2(bak, restored)
        rconn = sqlite3.connect(str(restored))
        try:
            n = rconn.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0]
            ver = rconn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
            ik = rconn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            rconn.close()
        return {
            "ok": True,
            "src_rows": len(n_src),
            "restored_rows": int(n),
            "restored_schema_version": str(ver),
            "restored_integrity": ik,
            "method": "sqlite3.Connection.backup",
            "authoritative_db_mutated": False,
        }
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main() -> int:
    report = {
        "authoritative_inspect": inspect_readonly(AUTH),
        "disposable_backup_selftest": disposable_backup_restore_selftest(),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
