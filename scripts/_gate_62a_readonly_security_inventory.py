"""Gate 62A: write sanitized read-only security inventory to local docs path. No DDL/DML."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref

OUT = ROOT / "docs" / "implementation" / "PHASE_4D_GATE_62A_SECURITY_INVENTORY_SNAPSHOT.json"


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    raw = os.environ.get("DATABASE_URL") or ""
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    if ref != "wmirifmgaftassgrfbyl":
        print("ABORT unexpected project", ref)
        return 2

    eng = create_engine(normalize_database_url(raw), pool_pre_ping=True, future=True)
    snap: dict = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_ref": ref,
        "host_redacted": info.host,
        "region_hint": "ap-southeast-2" if "ap-southeast-2" in (info.host or "") else None,
        "note": "Sanitized inventory — no passwords, URLs with credentials, or role passwords.",
    }

    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        snap["server_version"] = conn.execute(text("SHOW server_version")).scalar()
        snap["current_user"] = conn.execute(text("SELECT current_user")).scalar()
        snap["alembic"] = conn.execute(
            text("SELECT version_num FROM app.alembic_version LIMIT 1")
        ).scalar()
        snap["roles"] = [
            {
                "rolname": r[0],
                "rolsuper": r[1],
                "rolbypassrls": r[2],
                "rolcanlogin": r[3],
                "rolinherit": r[4],
            }
            for r in conn.execute(
                text(
                    """
                    SELECT rolname, rolsuper, rolbypassrls, rolcanlogin, rolinherit
                    FROM pg_roles
                    WHERE rolname = ANY(:names) OR rolname LIKE 'cryptonova_%'
                    ORDER BY 1
                    """
                ),
                {
                    "names": [
                        "postgres",
                        "authenticated",
                        "anon",
                        "authenticator",
                    ]
                },
            ).fetchall()
        ]
        snap["cryptonova_role_count"] = conn.execute(
            text("SELECT COUNT(*) FROM pg_roles WHERE rolname LIKE 'cryptonova_%'")
        ).scalar()
        snap["tables"] = [
            {
                "schema": r[0],
                "name": r[1],
                "owner": r[2],
                "rls": r[3],
                "force_rls": r[4],
            }
            for r in conn.execute(
                text(
                    """
                    SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner),
                           c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'app' AND c.relkind = 'r'
                    ORDER BY 1, 2
                    """
                )
            ).fetchall()
        ]
        snap["policies"] = [
            {
                "table": r[0],
                "policy": r[1],
                "cmd": r[2],
                "roles": r[3],
                "using": r[4],
                "with_check": r[5],
            }
            for r in conn.execute(
                text(
                    """
                    SELECT tablename, policyname, cmd, roles::text, qual, with_check
                    FROM pg_policies
                    WHERE schemaname = 'app'
                    ORDER BY 1, 2
                    """
                )
            ).fetchall()
        ]
        snap["phase4d_counts"] = {}
        for t in (
            "signal_history",
            "signal_agent_contributions",
            "signal_risk_events",
            "scheduler_evaluation_history",
            "scheduler_audit",
        ):
            snap["phase4d_counts"][t] = conn.execute(
                text(f"SELECT COUNT(*) FROM app.{t}")
            ).scalar()
        snap["auth_uid_exists"] = conn.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1 FROM pg_proc p
                  JOIN pg_namespace n ON n.oid = p.pronamespace
                  WHERE n.nspname = 'auth' AND p.proname = 'uid'
                )
                """
            )
        ).scalar()

    OUT.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT.as_posix())
    print("alembic", snap["alembic"])
    print("server_version", snap["server_version"])
    print("cryptonova_role_count", snap["cryptonova_role_count"])
    print("phase4d_counts", snap["phase4d_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
