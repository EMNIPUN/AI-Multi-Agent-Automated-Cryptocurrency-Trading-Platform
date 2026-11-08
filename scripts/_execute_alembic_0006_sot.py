"""Apply Alembic 20261108_0006 (Supabase SoT tables) on approved dev project.

Session-only migration window. Restores CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false.
Does NOT enable live trading or exchange orders.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref

EXPECTED_PROJECT = "wmirifmgaftassgrfbyl"
EXPECTED_BEFORE = "20261108_0005"
EXPECTED_AFTER = "20261108_0006"


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    raw = os.environ.get("DATABASE_URL") or ""
    if not raw.strip():
        print("FAIL:DATABASE_URL_missing")
        return 2
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    if ref != EXPECTED_PROJECT:
        print(f"FAIL:project_ref_mismatch:{ref}")
        return 2

    os.environ["CRYPTONOVA_DB_TARGET"] = "development"
    os.environ["CRYPTONOVA_DEV_PROJECT_REF"] = EXPECTED_PROJECT
    os.environ["CRYPTONOVA_USE_DATABASE_URL_AS_DEV"] = "true"
    os.environ["CRYPTONOVA_ALLOW_DEV_MIGRATIONS"] = "yes"

    url = normalize_database_url(raw, require_ssl_for_remote=True)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as c:
        rev = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        if rev == EXPECTED_AFTER:
            print(f"OK:already_at:{rev}")
            os.environ["CRYPTONOVA_ALLOW_DEV_MIGRATIONS"] = "false"
            return 0
        if rev != EXPECTED_BEFORE:
            print(f"FAIL:remote_revision_unexpected:{rev}")
            os.environ["CRYPTONOVA_ALLOW_DEV_MIGRATIONS"] = "false"
            return 2

    env = os.environ.copy()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "apps" / "api" / "alembic.ini"),
            "upgrade",
            EXPECTED_AFTER,
        ],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    os.environ["CRYPTONOVA_ALLOW_DEV_MIGRATIONS"] = "false"
    if proc.returncode != 0:
        print(f"FAIL:alembic_exit:{proc.returncode}")
        return proc.returncode

    with engine.connect() as c:
        rev = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        print(f"OK:revision:{rev}")
        if rev != EXPECTED_AFTER:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
