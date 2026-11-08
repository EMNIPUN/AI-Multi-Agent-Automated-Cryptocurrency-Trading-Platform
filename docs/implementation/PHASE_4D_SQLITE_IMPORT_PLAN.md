# Phase 4D — SQLite Import Plan (Dry-Run Only)

## Tool

`scripts/phase4d_sqlite_import_dry_run.py`

- Counts rows, duplicates, missing fields, outbox payload versions  
- Validates optional owner UUID format only  
- `--execute-cloud-import` is **refused**  

## Legacy handling

- Full `signal_history` rows retain contributions/risk/market JSON locally.  
- Legacy outbox summaries cannot reconstruct CoordinatorDecision → `PERMANENT_FAILURE` on sync; rebuild from local history during approved import.  
- Never fabricate missing indicators.  

## Gate E

Cloud import requires separate operator approval after backup verification and DDL apply. Do not delete SQLite files.
