"""
Offline audit of Alembic migrations vs SQLAlchemy models.

Does not connect to any database. Does not call Base.metadata.create_all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from apps.api.app.database_url import APP_SCHEMA
from apps.api.app.models import Base

_FORBIDDEN_SCHEMA_TOKENS = (
    "schema=\"auth\"",
    "schema='auth'",
    "schema=\"storage\"",
    "schema='storage'",
    "schema=\"realtime\"",
    "schema='realtime'",
    "schema=\"extensions\"",
    " CREATE SCHEMA auth",
    " DROP SCHEMA auth",
    "CREATE SCHEMA storage",
    "DROP SCHEMA storage",
)

_INITIAL_REVISION = "20261104_0001_initial_app_schema.py"
_OWNERSHIP_REVISION = "20261104_0002_ownership_rls.py"


@dataclass(frozen=True)
class MigrationAuditResult:
    ok: bool
    revision_files: list[str]
    model_tables: list[str]
    issues: list[str]


def _versions_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _all_revision_text(versions: Path) -> str:
    parts: list[str] = []
    for path in sorted(versions.glob("*.py")):
        if path.name == "__init__.py":
            continue
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def model_table_keys() -> set[str]:
    return set(Base.metadata.tables.keys())


def model_columns(table_key: str) -> set[str]:
    table = Base.metadata.tables[table_key]
    return {c.name for c in table.columns}


def audit_initial_migration() -> MigrationAuditResult:
    versions = _versions_dir()
    issues: list[str] = []
    files = sorted(p.name for p in versions.glob("*.py") if p.name != "__init__.py")
    initial = versions / _INITIAL_REVISION
    if not initial.is_file():
        return MigrationAuditResult(
            ok=False,
            revision_files=files,
            model_tables=sorted(model_table_keys()),
            issues=[f"missing initial revision {_INITIAL_REVISION}"],
        )

    text = initial.read_text(encoding="utf-8")
    all_text = _all_revision_text(versions)
    upper = text.upper()

    if "CREATE SCHEMA IF NOT EXISTS APP" not in upper:
        issues.append("initial migration must create schema app")
    if "def upgrade()" not in text or "def downgrade()" not in text:
        issues.append("upgrade/downgrade must both be defined")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"DROP\s+SCHEMA\s+.*\bCASCADE\b", stripped, flags=re.IGNORECASE):
            issues.append("refuse CASCADE schema drops in initial migration")
            break

    for token in _FORBIDDEN_SCHEMA_TOKENS:
        if token.lower() in all_text.lower():
            issues.append(f"migration must not touch foreign schema token: {token}")

    expected_tables = {
        f"{APP_SCHEMA}.agent_decisions",
        f"{APP_SCHEMA}.system_events",
        f"{APP_SCHEMA}.strategy_configs",
    }
    model_tables = model_table_keys()
    if model_tables != expected_tables:
        issues.append(
            f"model tables mismatch: {sorted(model_tables)} vs {sorted(expected_tables)}"
        )

    for key in expected_tables:
        short = key.split(".", 1)[1]
        if not re.search(rf"create_table\(\s*[\"']{re.escape(short)}[\"']", text):
            issues.append(f"migration missing create_table for {short}")

        cols = model_columns(key)
        for col in cols:
            # Columns may land in later revisions (e.g. owner_user_id in 0002).
            if f'"{col}"' not in all_text and f"'{col}'" not in all_text:
                issues.append(f"{short}: model column {col} missing from migration source")

    # Indexes / unique from models — allow across revision chain.
    for key in expected_tables:
        table = Base.metadata.tables[key]
        for idx in table.indexes:
            if idx.name and idx.name not in all_text:
                issues.append(f"index {idx.name} missing from migration source")

    # No FK targets outside app (none expected in 2A/2B/2D).
    for key in expected_tables:
        table = Base.metadata.tables[key]
        for fk in table.foreign_keys:
            ref_table = fk.column.table
            if ref_table.schema and ref_table.schema != APP_SCHEMA:
                issues.append(f"FK from {key} references non-app schema")

    if "schema=\"app\"" not in text and "schema='app'" not in text:
        issues.append("create_table calls must set schema='app'")

    return MigrationAuditResult(
        ok=len(issues) == 0,
        revision_files=files,
        model_tables=sorted(model_tables),
        issues=issues,
    )


def audit_ownership_migration() -> MigrationAuditResult:
    """Offline checks for Phase 2D ownership + RLS revision."""
    versions = _versions_dir()
    issues: list[str] = []
    files = sorted(p.name for p in versions.glob("*.py") if p.name != "__init__.py")
    path = versions / _OWNERSHIP_REVISION
    if not path.is_file():
        return MigrationAuditResult(
            ok=False,
            revision_files=files,
            model_tables=sorted(model_table_keys()),
            issues=[f"missing ownership revision {_OWNERSHIP_REVISION}"],
        )

    text = path.read_text(encoding="utf-8")
    if 'down_revision' not in text or "20261104_0001" not in text:
        issues.append("ownership revision must revise 20261104_0001")
    if "owner_user_id" not in text:
        issues.append("ownership revision must add owner_user_id")
    if "ENABLE ROW LEVEL SECURITY" not in text.upper():
        issues.append("ownership revision must enable RLS")
    if "FORCE ROW LEVEL SECURITY" in text.upper():
        issues.append("do not FORCE RLS on table owner without operator review")
    if "GRANT " in text.upper() and "GRANT USAGE ON SCHEMA" in text.upper():
        issues.append("ownership revision must not GRANT schema USAGE broadly")
    if "auth.uid()" not in text:
        issues.append("RLS policies should use auth.uid() for authenticated role")
    if "owner_user_id IS NOT NULL" not in text:
        issues.append("RLS / unique index should treat NULL owners carefully")
    for token in _FORBIDDEN_SCHEMA_TOKENS:
        if token.lower() in text.lower():
            issues.append(f"ownership migration foreign schema token: {token}")
    # Destructive patterns
    if re.search(r"DROP\s+TABLE", text, flags=re.IGNORECASE):
        issues.append("ownership upgrade must not DROP TABLE")
    if re.search(r"TRUNCATE\s+", text, flags=re.IGNORECASE):
        issues.append("ownership upgrade must not TRUNCATE")

    return MigrationAuditResult(
        ok=len(issues) == 0,
        revision_files=files,
        model_tables=sorted(model_table_keys()),
        issues=issues,
    )
