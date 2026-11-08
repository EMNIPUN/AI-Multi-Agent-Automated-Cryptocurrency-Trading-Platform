# Phase 4D Gate B0 — SQLite v4 Backup Review

**Authoritative path:** `data/multi_agent_signals.sqlite3`  
**Inspection mode:** read-only (`mode=ro`) + disposable fixture self-test  
**Authoritative DB mutated:** no

## Authoritative inspection (2026-11-07)

| Check | Evidence | Result | Severity | Blocking |
| --- | --- | --- | --- | --- |
| File exists | size 106496 bytes | PASS | — | No |
| Schema version | `schema_meta.schema_version = 4` | PASS | — | No |
| Integrity | `PRAGMA integrity_check = ok` | PASS | High if fail | No |
| WAL presence | `-wal` exists (0 bytes), `-shm` exists; RO probe `journal_mode=wal` | PASS | — | No |
| History preserved | `signal_history` count = **3** | PASS | — | No |
| Risk state preserved | `paper_risk_state` count = **1** | PASS | — | No |
| Checkpoints | `evaluation_checkpoints` = 0 | PASS (empty OK) | — | No |
| Outbox table v4 | columns include `lease_until_ms` | PASS | — | No |
| Outbox rows | count = **0** | PASS / note | Medium for sync | No for DDL |
| Scheduler lock/audit | 0 rows | PASS (empty OK) | — | No |

## v3 → v4 migration (code review)

Implementation in `SignalHistoryStore._init_db`:

- Additive `ALTER TABLE … ADD COLUMN lease_until_ms` (ignores if present)  
- Status normalize: `pending→PENDING`, `failed→RETRY_WAIT`, `synced→SYNCED`  
- Does **not** drop history, risk, checkpoints, or outbox payloads  
- Schema version written to `4` after migrations  

**Result: PASS** for non-destructive local upgrade design.

## Safe backup procedure (WAL-aware)

**Do not** rely on copying only the `.sqlite3` file while the API holds a live WAL writer without checkpoint/backup API.

Preferred (online-safe):

```powershell
# From repo root — stops nothing; uses SQLite backup API against a short-lived connection.
# Prefer stopping the API process first for a quiet copy window when practical.
uv run python -c "import sqlite3,time; from pathlib import Path; src=Path('data/multi_agent_signals.sqlite3'); bak=Path('data/backups')/f'multi_agent_signals_{int(time.time())}.sqlite3'; bak.parent.mkdir(parents=True, exist_ok=True); s=sqlite3.connect(str(src)); d=sqlite3.connect(str(bak)); s.backup(d); d.close(); s.close(); print(bak)"
```

After backup: verify with `PRAGMA integrity_check` on the backup file only.

## Disposable self-test (this session)

| Check | Result |
| --- | --- |
| `sqlite3.Connection.backup` fixture | PASS |
| Restored row count matches | PASS |
| Restored schema_version = 4 | PASS |
| Restored integrity_check = ok | PASS |
| Authoritative DB touched | **false** |

## Required operator action

Create a timestamped backup of the authoritative SQLite DB via the backup API (or stop API + verified backup) **before** any future cloud import or risky local surgery. Not required to *apply* empty cloud DDL, but required before Gate E.
