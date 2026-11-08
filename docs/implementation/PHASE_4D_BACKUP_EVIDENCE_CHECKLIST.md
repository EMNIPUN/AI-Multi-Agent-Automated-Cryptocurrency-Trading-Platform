# Phase 4D Gate B0 — Backup Evidence Checklist

**Status: BACKUP NOT VERIFIED**  
**Blocking: YES (mandatory for unqualified migration GO)**  
**Severity: High**

## What this session established

| Item | Evidence | PASS / FAIL / NOT VERIFIED |
| --- | --- | --- |
| Usable Supabase backup exists | No dashboard evidence recorded; prior Phase 3C Gate B also unverified | **NOT VERIFIED** |
| Backup timestamp | — | **NOT VERIFIED** |
| Backup retention | — | **NOT VERIFIED** |
| PITR available | — | **NOT VERIFIED** |
| Restore tested | — | **NOT VERIFIED** |
| RPO documented | — | **NOT VERIFIED** |
| RTO documented | — | **NOT VERIFIED** |

Do **not** infer backup availability from plan tier, marketing labels, or “Backups” menu visibility alone.

## Operator manual steps (read-only; no cloud state change)

In **Supabase Dashboard** → project **`wmirifmgaftassgrfbyl`** (confirm project ref in Settings → General):

1. Open **Project Settings → Infrastructure** (or **Database → Backups**, depending on UI version).  
2. Record whether **daily backups** and/or **Point-in-Time Recovery (PITR)** are enabled.  
3. Note the **latest backup / recovery window** timestamp and retention period.  
4. Open restore UI if present and confirm a restore target can be selected **without clicking Confirm/Restore**.  
5. Write down personal RPO/RTO targets (e.g. RPO ≤ 24h, RTO ≤ 4h for this personal project).  
6. Optionally schedule a restore test into a **disposable** project later — that is a separate approved activity.

**Do not** paste connection strings, service-role keys, or credential screenshots into chat or git.

## Required operator action

Complete the checklist above and file evidence (timestamps + yes/no answers only) before requesting Gate B migration approval. Until then Gate B0 remains **NO-GO** on backup.
