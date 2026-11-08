#!/usr/bin/env python3
"""
Phase 4D — SQLite → Supabase signal import planner (DRY-RUN by default).

Never writes to Supabase. Never deletes SQLite files.

Usage:
  python scripts/phase4d_sqlite_import_dry_run.py
  python scripts/phase4d_sqlite_import_dry_run.py --db data/multi_agent_signals.sqlite3
  python scripts/phase4d_sqlite_import_dry_run.py --owner-user-id <uuid>  # validation only

Cloud import requires explicit operator approval + applied DDL + dual gates.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def plan_import(db_path: Path) -> dict:
    if not db_path.exists():
        return {
            "ok": False,
            "error": "sqlite_missing",
            "db_path": str(db_path),
            "would_write_supabase": False,
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        meta = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        schema_version = int(meta["value"]) if meta else None
        signal_n = conn.execute("SELECT COUNT(*) AS n FROM signal_history").fetchone()["n"]
        by_action = {
            r["action"]: r["n"]
            for r in conn.execute(
                "SELECT action, COUNT(*) AS n FROM signal_history GROUP BY action"
            )
        }
        by_version = {
            r["strategy_version"]: r["n"]
            for r in conn.execute(
                "SELECT strategy_version, COUNT(*) AS n FROM signal_history GROUP BY strategy_version"
            )
        }
        risk = conn.execute("SELECT halted, corrupt, day_key FROM paper_risk_state WHERE id = 1").fetchone()
        cp_n = 0
        audit_n = 0
        outbox_n = 0
        try:
            cp_n = conn.execute("SELECT COUNT(*) AS n FROM evaluation_checkpoints").fetchone()["n"]
        except sqlite3.Error:
            pass
        try:
            audit_n = conn.execute("SELECT COUNT(*) AS n FROM scheduler_audit").fetchone()["n"]
        except sqlite3.Error:
            pass
        try:
            outbox_n = conn.execute("SELECT COUNT(*) AS n FROM cloud_sync_outbox").fetchone()["n"]
        except sqlite3.Error:
            pass

        # Idempotency sample: duplicate decision_id / idempotent_key must be zero locally.
        dup_dec = conn.execute(
            """
            SELECT COUNT(*) AS n FROM (
              SELECT decision_id FROM signal_history GROUP BY decision_id HAVING COUNT(*) > 1
            )
            """
        ).fetchone()["n"]
        dup_idem = conn.execute(
            """
            SELECT COUNT(*) AS n FROM (
              SELECT idempotent_key FROM signal_history GROUP BY idempotent_key HAVING COUNT(*) > 1
            )
            """
        ).fetchone()["n"]

        missing_fields = 0
        sample = conn.execute(
            """
            SELECT decision_id, symbol, category, interval, action, strategy_version,
                   contributions_json, risk_json, market_json
            FROM signal_history ORDER BY timestamp_ms ASC LIMIT 200
            """
        ).fetchall()
        for r in sample:
            for col in ("decision_id", "symbol", "category", "interval", "action", "strategy_version"):
                if not r[col]:
                    missing_fields += 1

        outbox_payload_versions: dict[str, int] = {}
        legacy_outbox = 0
        try:
            for r in conn.execute(
                "SELECT payload_json FROM cloud_sync_outbox ORDER BY id ASC LIMIT 500"
            ):
                try:
                    payload = json.loads(r["payload_json"] or "{}")
                except json.JSONDecodeError:
                    payload = {}
                ver = str(payload.get("payload_schema_version") or "legacy_summary")
                outbox_payload_versions[ver] = outbox_payload_versions.get(ver, 0) + 1
                if "decision" not in payload:
                    legacy_outbox += 1
        except sqlite3.Error:
            pass

        return {
            "ok": True,
            "mode": "dry_run",
            "would_write_supabase": False,
            "db_path": str(db_path.resolve()),
            "sqlite_schema_version": schema_version,
            "row_counts": {
                "signal_history": signal_n,
                "evaluation_checkpoints": cp_n,
                "scheduler_audit": audit_n,
                "cloud_sync_outbox": outbox_n,
            },
            "by_action": by_action,
            "by_strategy_version": by_version,
            "paper_risk": {
                "halted": bool(risk["halted"]) if risk else None,
                "corrupt": bool(risk["corrupt"]) if risk else None,
                "day_key": risk["day_key"] if risk else None,
                "authority": "local_sqlite_retained",
            },
            "idempotency_check": {
                "duplicate_decision_id_groups": dup_dec,
                "duplicate_idempotent_key_groups": dup_idem,
                "pass": dup_dec == 0 and dup_idem == 0,
            },
            "missing_field_hits_in_sample": missing_fields,
            "outbox_payload_versions": outbox_payload_versions,
            "legacy_outbox_rows": legacy_outbox,
            "legacy_handling": (
                "Legacy summary outbox rows cannot reconstruct full CoordinatorDecision; "
                "mark PERMANENT_FAILURE and rebuild from local signal_history contributions_json "
                "during an approved import — never fabricate missing indicators."
            ),
            "owner_mapping_validation": (
                "Import owner must be verified Supabase Auth JWT sub / "
                "SIGNAL_CLOUD_OWNER_USER_ID — never invented."
            ),
            "backup_instructions": [
                f"Copy '{db_path}' to a timestamped backup before any future import.",
                "Keep the original SQLite file; import is upsert-only and must not delete local rows.",
                "Do not set SIGNAL_SUPABASE_WRITES_* until DDL 20261107_0004 is operator-approved and applied.",
            ],
            "resume_support": (
                "Future import will key on decision_id / owner+idempotent_key UNIQUE constraints."
            ),
            "blocked_until": [
                "operator_approval_for_cloud_ddl",
                "alembic_20261107_0004_applied",
                "SIGNAL_SUPABASE_WRITES_ENABLED=true",
                "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED=true",
                "authenticated_owner_user_id_for_import_scope",
                "Gate E historical import approval",
            ],
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4D SQLite import dry-run planner")
    parser.add_argument(
        "--db",
        default="data/multi_agent_signals.sqlite3",
        help="Path to local signal SQLite DB",
    )
    parser.add_argument(
        "--owner-user-id",
        default="",
        help="Optional UUID to include in the plan (not written)",
    )
    parser.add_argument(
        "--execute-cloud-import",
        action="store_true",
        help="REFUSED — cloud import is disabled in this script",
    )
    args = parser.parse_args(argv)

    if args.execute_cloud_import:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "cloud_import_refused_until_operator_approval",
                    "would_write_supabase": False,
                },
                indent=2,
            )
        )
        return 2

    report = plan_import(Path(args.db))
    if args.owner_user_id:
        report["planned_owner_user_id"] = args.owner_user_id
        report["owner_note"] = (
            "Owner must come from verified Supabase Auth JWT at import time — "
            "never from an untrusted CLI flag in production paths."
        )
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
