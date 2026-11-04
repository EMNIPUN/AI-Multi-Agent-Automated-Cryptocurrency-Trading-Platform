# Migration SQL review artifacts

Generated offline for operator review (localhost placeholder URL only — not production credentials).

- `20261104_0001_upgrade_head.sql` — initial app schema; **do not treat as auto-applied**
- `20261104_0002_ownership_rls.sql` — owner_user_id + RLS; **do not treat as auto-applied**

Regenerate (example):

```powershell
$env:DATABASE_URL = "postgresql://review_only:unused@127.0.0.1:5432/postgres"
uv run alembic -c apps/api/alembic.ini upgrade head --sql | Set-Content -Encoding utf8 apps/api/sql/review/alembic_head_offline.sql
```

Never commit real passwords into this folder.
Never run these scripts against remote Supabase without explicit operator approval.
