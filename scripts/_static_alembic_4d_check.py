"""Static-only Alembic chain check for Phase 4D preflight (no DB, no upgrade)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "apps" / "api" / "alembic" / "versions"
PROPOSED = (
    ROOT
    / "apps"
    / "api"
    / "alembic"
    / "versions_proposed"
    / "20261107_0004_phase4d_signal_persistence.py"
)


def _rev_from_file(path: Path) -> tuple[str | None, object]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    rev = down = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "revision" and node.value is not None:
                rev = ast.literal_eval(node.value)
            if node.target.id == "down_revision" and node.value is not None:
                down = ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "revision":
                    rev = ast.literal_eval(node.value)
                if isinstance(t, ast.Name) and t.id == "down_revision":
                    down = ast.literal_eval(node.value)
    return rev, down


def main() -> int:
    active: dict[str, tuple[object, object]] = {}
    for f in sorted(VERSIONS.glob("*.py")):
        if f.name.startswith("__"):
            continue
        rev, down = _rev_from_file(f)
        active[f.name] = (rev, down)
        print(f"active {f.name}: revision={rev} down_revision={down}")

    revs = {rev for rev, _ in active.values() if rev}
    downs = {down for _, down in active.values() if down}
    heads = sorted(revs - downs)
    print(f"active_heads={heads}")

    prev, pdown = _rev_from_file(PROPOSED)
    print(f"proposed: revision={prev} down_revision={pdown}")
    print(f"proposed_dir={PROPOSED.parent.name}")
    print(f"discoverable_by_default_alembic={PROPOSED.parent.name == 'versions'}")
    print(f"down_matches_active_head={pdown in heads}")

    proposed_text = PROPOSED.read_text(encoding="utf-8")
    tables = re.findall(r'create_table\(\s*"([^"]+)"', proposed_text)
    print(f"proposed_tables={tables}")
    conflicts = []
    for f in VERSIONS.glob("*.py"):
        t = f.read_text(encoding="utf-8")
        for table in tables:
            if f'"{table}"' in t and "create_table" in t:
                # coarse: only if create_table for same name exists
                if re.search(rf'create_table\(\s*"{re.escape(table)}"', t):
                    conflicts.append((table, f.name))
    print(f"table_name_conflicts_with_active={conflicts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
