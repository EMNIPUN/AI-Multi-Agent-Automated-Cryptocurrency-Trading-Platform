"""Offline review of generated Alembic SQL — no network, no secret printing."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.migration_audit import audit_initial_migration  # noqa: E402

SQL = ROOT / "apps" / "api" / "sql" / "review" / "20261104_0001_upgrade_head.sql"


def main() -> int:
    if not SQL.is_file():
        print("missing_sql_artifact")
        return 1
    text = SQL.read_text(encoding="utf-8")
    upper = text.upper()
    checks = {
        "sql_bytes": SQL.stat().st_size,
        "has_create_schema_app": "CREATE SCHEMA IF NOT EXISTS APP" in upper
        or "CREATE SCHEMA IF NOT EXISTS app" in text,
        "has_agent_decisions": "agent_decisions" in text,
        "has_system_events": "system_events" in text,
        "has_strategy_configs": "strategy_configs" in text,
        "has_alembic_version": "alembic_version" in text,
        "schema_qualified_app": "app." in text.lower() or 'SCHEMA = "app"' in text or "schema='app'" in text or 'SCHEMA "app"' in text or "SCHEMA app" in upper,
        "touches_auth": bool(re.search(r"\bSCHEMA\s+auth\b", text, re.I)),
        "touches_storage": bool(re.search(r"\bSCHEMA\s+storage\b", text, re.I)),
        "touches_realtime": bool(re.search(r"\bSCHEMA\s+realtime\b", text, re.I)),
        "drop_schema_cascade": bool(re.search(r"DROP\s+SCHEMA\s+.*\bCASCADE\b", text, re.I)),
        "contains_insert_version": "20261104_0001" in text,
    }
    # Credential-ish tokens that must not appear in review SQL
    leak_hits = [
        t
        for t in ("cryptonova", "bybit_api", "api_secret", "service_role")
        if t in text.lower()
    ]
    audit = audit_initial_migration()
    for k, v in checks.items():
        print(f"{k}={v}")
    print(f"leak_hits={leak_hits}")
    print(f"audit_ok={audit.ok}")
    print(f"audit_issues={audit.issues}")
    ok = (
        checks["has_create_schema_app"]
        and checks["has_agent_decisions"]
        and checks["has_system_events"]
        and checks["has_strategy_configs"]
        and checks["has_alembic_version"]
        and not checks["touches_auth"]
        and not checks["touches_storage"]
        and not checks["touches_realtime"]
        and not checks["drop_schema_cascade"]
        and not leak_hits
        and audit.ok
    )
    print(f"review_ok={ok}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
