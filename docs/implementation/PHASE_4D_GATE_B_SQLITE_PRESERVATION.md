# Phase 4D Gate B — SQLite v4 Preservation

**Authoritative DB:** `data/multi_agent_signals.sqlite3`  
**Mutated this session:** **no**

## Latest read-only inspection

| Metric | Value |
| --- | --- |
| schema_version | 4 |
| integrity_check | ok |
| journal_mode (RO probe) | wal |
| signal_history | 3 |
| paper_risk_state | 1 |
| cloud_sync_outbox | 0 |
| evaluation_checkpoints | 0 |
| outbox `lease_until_ms` column | present |

Disposable fixture: `sqlite3.Connection.backup` self-test **PASS** (authoritative untouched).

## Future backup destination / naming

```text
data/backups/multi_agent_signals_YYYYMMDD_HHMMSS.sqlite3
```

Use the SQLite **backup API** (accounts for WAL). Do not copy only the main file while a writer holds an active WAL.

### Documented future command (NOT EXECUTED as part of claiming a real backup here)

```powershell
# Prefer stopping the API first for a quiet window.
New-Item -ItemType Directory -Force data\backups | Out-Null
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
uv run python -c "import sqlite3; from pathlib import Path; src=Path('data/multi_agent_signals.sqlite3'); bak=Path('data/backups')/f'multi_agent_signals_$ts.sqlite3'; s=sqlite3.connect(str(src)); d=sqlite3.connect(str(bak)); s.backup(d); d.close(); s.close(); print(bak)"
```

Replace `$ts` appropriately in the one-liner or set env before running.

### Post-backup verification

- `PRAGMA integrity_check` on backup = `ok`  
- Compare counts: signal_history, paper_risk_state, cloud_sync_outbox, evaluation_checkpoints  
- Confirm `schema_meta.schema_version` = 4  

**Claim status:** procedure **prepared** and fixture-tested; **no claim** that a new authoritative backup file was created in this Gate B prep unless the operator runs the command.
