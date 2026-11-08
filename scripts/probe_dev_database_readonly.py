"""Read-only development DB probe — prints non-secret identity/schema facts only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine, text

from apps.api.app.database_url import normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref


def main() -> int:
    raw = (os.environ.get("DATABASE_URL") or os.environ.get("DEV_DATABASE_URL") or "").strip()
    if not raw:
        print("NO_DATABASE_URL")
        return 2
    url = normalize_database_url(raw)
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        ver = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        print("ALEMBIC_VERSION", ver)
        tables = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='app' ORDER BY 1"
                )
            )
        ]
        print("APP_TABLES", ",".join(tables))
        for t in (
            "agent_decisions",
            "system_events",
            "strategy_configs",
            "exchange_account_bindings",
        ):
            if t not in tables:
                print(f"COUNT_{t}", "MISSING")
                continue
            n = conn.execute(text(f"SELECT COUNT(*) FROM app.{t}")).scalar()
            print(f"COUNT_{t}", n)
        cols = list(
            conn.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.columns
                    WHERE table_schema='app' AND column_name='owner_user_id'
                    ORDER BY 1
                    """
                )
            )
        )
        print("OWNER_USER_ID_TABLES", ",".join(r[0] for r in cols) or "NONE")
        rls = list(
            conn.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'app' AND c.relkind = 'r'
                    ORDER BY 1
                    """
                )
            )
        )
        for name, enabled in rls:
            print(f"RLS_{name}", bool(enabled))
        pols = list(
            conn.execute(
                text(
                    """
                    SELECT tablename, policyname
                    FROM pg_policies WHERE schemaname='app'
                    ORDER BY 1, 2
                    """
                )
            )
        )
        print("POLICY_COUNT", len(pols))
        for t, p in pols:
            print("POLICY", t, p)
        who = conn.execute(text("SELECT current_user, current_database()")).one()
        print("CURRENT_USER", who[0])
        print("CURRENT_DATABASE", who[1])
        print(
            "HAS_CREATE",
            conn.execute(
                text("SELECT has_schema_privilege(current_user, 'app', 'CREATE')")
            ).scalar(),
        )
        auth_role = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated')")
        ).scalar()
        print("AUTHENTICATED_ROLE_EXISTS", bool(auth_role))
        # strategy name unique index presence
        idx = list(
            conn.execute(
                text(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE schemaname='app' AND tablename='strategy_configs'
                    ORDER BY 1
                    """
                )
            )
        )
        print("STRATEGY_INDEXES", ",".join(r[0] for r in idx) or "NONE")
    eng.dispose()
    # identity from URL without secrets
    from apps.api.app.database_url import inspect_database_url

    info = inspect_database_url(raw)
    print("HOST", info.host)
    print("PROJECT_REF", extract_project_ref(host=info.host, user=info.user))
    print("READ_ONLY_PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
