# Phase 4D Gate 62 — Execution Authorization Draft

```
╔══════════════════════════════════════════════════════════════╗
║  HISTORICAL DRAFT — Gate 62 WAS AUTHORIZED AND EXECUTED      ║
║  See PHASE_4D_GATE_62_EXECUTION_REPORT.md (MIGRATION_VERIFIED)║
║  Do NOT re-run upgrade without a new explicit approval.      ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Suggested operator message (copy/adapt only when ready)

> I authorize **Gate 62 execution** for CryptoNova development Supabase project **`wmirifmgaftassgrfbyl`** (`ap-southeast-2`) only.  
>  
> Apply Alembic revision **`20261108_0005`** from  
> `apps/api/alembic/versions_proposed/20261108_0005_option_a_least_privilege.py`  
> after confirming SHA-256 equals  
> **`9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a`**.  
>  
> **Approved DDL scope:** create `cryptonova_api_runtime` and `cryptonova_migrator` (NOLOGIN, NOBYPASSRLS, INHERIT); schema/table/function grants; runtime RLS SELECT/INSERT/UPDATE on signal tables; SELECT-only on scheduler/catalog; migrator DML + CREATE ON SCHEMA app; Alembic metadata → `20261108_0005`.  
>  
> **Expected application signal row changes: ZERO.**  
> Alembic version bookkeeping may update.  
>  
> I accept that Supabase managed backup / PITR was **not independently verified** in Gate 62 review, and that Alembic downgrade will not fully DROP roles.  
>  
> **Explicitly NOT authorized:**  
> - Gate 63 FastAPI runtime credential cutover  
> - Gate C2 synthetic / any cloud signal writes  
> - Cloud sync / historical import  
> - Exchange Testnet or Mainnet orders  
> - Deployment or git push  
>  
> **Stop if:** wrong project, checksum mismatch, Alembic ≠ `20261107_0004` before apply, CREATE ROLE/GRANT/POLICY failure, unexpected Phase 4D row growth, or any write/sync/order flag found ON.  
>  
> After apply: run read-only verification scripts and leave FastAPI on the current privileged connection until a separate Gate 63 approval.

---

## Stop conditions (must appear in any real approval)

1. Project ref ≠ `wmirifmgaftassgrfbyl`
2. Migration SHA-256 mismatch
3. Pre-apply Alembic ≠ `20261107_0004`
4. Partial role/policy failure
5. Unexpected signal row counts
6. Cloud write / sync / order flags enabled

---

## Reminder

Until the operator pastes an explicit approval in a **new** chat turn (not this draft), Cursor must **not**:

- Promote the file into `alembic/versions/`
- Run `alembic upgrade`
- CREATE ROLE / GRANT / POLICY on Supabase
- Change runtime credentials
