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
_EXCHANGE_BINDING_REVISION = "20261105_0003_exchange_account_bindings.py"
_PHASE4D_SIGNAL_REVISION = "20261107_0004_phase4d_signal_persistence.py"

_CATALOG_TABLES = {
    f"{APP_SCHEMA}.agent_decisions",
    f"{APP_SCHEMA}.system_events",
    f"{APP_SCHEMA}.strategy_configs",
}
_EXCHANGE_BINDING_TABLE = f"{APP_SCHEMA}.exchange_account_bindings"
_PHASE4D_SIGNAL_TABLES = {
    f"{APP_SCHEMA}.signal_history",
    f"{APP_SCHEMA}.signal_agent_contributions",
    f"{APP_SCHEMA}.signal_risk_events",
    f"{APP_SCHEMA}.scheduler_evaluation_history",
    f"{APP_SCHEMA}.scheduler_audit",
}


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

    # Register Phase 4D ORM mappers when present so suite order does not flake.
    try:
        from apps.api.app.signals import cloud_models as _cloud_models  # noqa: F401
    except ImportError:
        pass

    expected_catalog = set(_CATALOG_TABLES)
    model_tables = model_table_keys()
    if not expected_catalog.issubset(model_tables):
        issues.append(
            f"catalog model tables missing: {sorted(expected_catalog - model_tables)}"
        )
    allowed_later = {_EXCHANGE_BINDING_TABLE} | _PHASE4D_SIGNAL_TABLES
    unexpected = model_tables - expected_catalog - allowed_later
    if unexpected:
        issues.append(f"unexpected model tables: {sorted(unexpected)}")

    for key in expected_catalog:
        short = key.split(".", 1)[1]
        if not re.search(rf"create_table\(\s*[\"']{re.escape(short)}[\"']", text):
            issues.append(f"migration missing create_table for {short}")

        cols = model_columns(key)
        for col in cols:
            # Columns may land in later revisions (e.g. owner_user_id in 0002).
            if f'"{col}"' not in all_text and f"'{col}'" not in all_text:
                issues.append(f"{short}: model column {col} missing from migration source")

    # Indexes / unique from models — allow across revision chain.
    for key in expected_catalog | ({_EXCHANGE_BINDING_TABLE} & model_tables):
        table = Base.metadata.tables[key]
        for idx in table.indexes:
            if idx.name and idx.name not in all_text:
                issues.append(f"index {idx.name} missing from migration source")

    # No FK targets outside app (none expected in 2A/2B/2D/3C).
    for key in model_tables:
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
        model_tables=sorted(model_table_keys()),
        issues=issues,
    )


def audit_exchange_binding_migration() -> MigrationAuditResult:
    """Offline checks for Phase 3C exchange-account binding revision."""
    versions = _versions_dir()
    issues: list[str] = []
    files = sorted(p.name for p in versions.glob("*.py") if p.name != "__init__.py")
    path = versions / _EXCHANGE_BINDING_REVISION
    if not path.is_file():
        return MigrationAuditResult(
            ok=False,
            revision_files=files,
            model_tables=sorted(model_table_keys()),
            issues=[f"missing exchange binding revision {_EXCHANGE_BINDING_REVISION}"],
        )

    text = path.read_text(encoding="utf-8")
    if "20261104_0002" not in text:
        issues.append("exchange binding revision must revise 20261104_0002")
    if "exchange_account_bindings" not in text:
        issues.append("must create exchange_account_bindings")
    if "credential_ref" not in text:
        issues.append("must include opaque credential_ref")
    if "telemetry_scope_id" not in text:
        issues.append("must include telemetry_scope_id")
    if "ENABLE ROW LEVEL SECURITY" not in text.upper():
        issues.append("exchange binding revision must enable RLS")
    if "FORCE ROW LEVEL SECURITY" in text.upper():
        issues.append("do not FORCE RLS without operator review")
    if "GRANT USAGE ON SCHEMA" in text.upper():
        issues.append("must not GRANT schema USAGE broadly")
    if "auth.uid()" not in text:
        issues.append("RLS policies should use auth.uid()")
    if "api_key" in text.lower() or "api_secret" in text.lower():
        issues.append("migration must not store raw api_key/api_secret columns")
    for token in _FORBIDDEN_SCHEMA_TOKENS:
        if token.lower() in text.lower():
            issues.append(f"foreign schema token: {token}")
    if re.search(r"DROP\s+TABLE", text, flags=re.IGNORECASE) and "downgrade" not in text.lower():
        # upgrade path must not drop tables; downgrade may
        upgrade_block = text.split("def downgrade", 1)[0]
        if re.search(r"DROP\s+TABLE", upgrade_block, flags=re.IGNORECASE):
            issues.append("exchange binding upgrade must not DROP TABLE")

    if _EXCHANGE_BINDING_TABLE not in model_table_keys():
        issues.append("SQLAlchemy model for exchange_account_bindings missing")
    else:
        cols = model_columns(_EXCHANGE_BINDING_TABLE)
        for required in (
            "owner_user_id",
            "provider",
            "environment",
            "status",
            "credential_ref",
            "telemetry_scope_id",
            "enrollment_attestation",
        ):
            if required not in cols:
                issues.append(f"model missing column {required}")

    return MigrationAuditResult(
        ok=len(issues) == 0,
        revision_files=files,
        model_tables=sorted(model_table_keys()),
        issues=issues,
    )


def audit_phase4d_signal_persistence_migration() -> MigrationAuditResult:
    """Offline checks for Phase 4D signal persistence revision (Gate B / C1)."""
    versions = _versions_dir()
    issues: list[str] = []
    files = sorted(p.name for p in versions.glob("*.py") if p.name != "__init__.py")
    path = versions / _PHASE4D_SIGNAL_REVISION
    if not path.is_file():
        return MigrationAuditResult(
            ok=False,
            revision_files=files,
            model_tables=sorted(model_table_keys()),
            issues=[f"missing Phase 4D revision {_PHASE4D_SIGNAL_REVISION}"],
        )

    try:
        from apps.api.app.signals import cloud_models as _cloud_models  # noqa: F401
    except ImportError:
        issues.append("cloud_models module missing")

    text = path.read_text(encoding="utf-8")
    if "20261105_0003" not in text:
        issues.append("Phase 4D revision must revise 20261105_0003")
    for short in (
        "signal_history",
        "signal_agent_contributions",
        "signal_risk_events",
        "scheduler_evaluation_history",
        "scheduler_audit",
    ):
        if short not in text:
            issues.append(f"must create {short}")
    if "ENABLE ROW LEVEL SECURITY" not in text.upper():
        issues.append("Phase 4D revision must enable RLS")
    if "FORCE ROW LEVEL SECURITY" in text.upper():
        issues.append("do not FORCE RLS without operator review")
    if "auth.uid()" not in text:
        issues.append("RLS policies should use auth.uid()")
    if "GRANT USAGE ON SCHEMA" in text.upper():
        issues.append("must not GRANT schema USAGE broadly")
    for token in _FORBIDDEN_SCHEMA_TOKENS:
        if token.lower() in text.lower():
            issues.append(f"foreign schema token: {token}")

    model_tables = model_table_keys()
    missing_models = _PHASE4D_SIGNAL_TABLES - model_tables
    if missing_models:
        issues.append(f"SQLAlchemy models missing: {sorted(missing_models)}")
    else:
        for key in _PHASE4D_SIGNAL_TABLES:
            short = key.split(".", 1)[1]
            cols = model_columns(key)
            if "owner_user_id" not in cols:
                issues.append(f"{short}: model missing owner_user_id")
            for col in cols:
                if f'"{col}"' not in text and f"'{col}'" not in text:
                    issues.append(f"{short}: model column {col} missing from migration")

    return MigrationAuditResult(
        ok=len(issues) == 0,
        revision_files=files,
        model_tables=sorted(model_table_keys()),
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
