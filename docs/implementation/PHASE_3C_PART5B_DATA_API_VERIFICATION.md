# Phase 3C Part 5B — Data API Verification

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Development project | `wmirifmgaftassgrfbyl` |
| Schema of concern | `app` |
| Modifications performed | **None** |

---

## Operator checklist (read-only)

Open the **Supabase Dashboard** for project `wmirifmgaftassgrfbyl`:

1. **Project Settings → API** (or **Data API Settings**, depending on Dashboard version).
2. Locate **Exposed schemas** / **Data API exposed schemas**.
3. Confirm whether `app` appears in the list.
4. Expected secure state: `app` is **not** exposed (typical defaults: `public`, optionally `graphql_public`).
5. Capture a screenshot that shows the exposed-schema list **without** revealing the `service_role` key or database password.
6. Store the screenshot locally (do not commit secrets).

---

## Why grants alone are insufficient

PostgreSQL catalog inspection (Part 5) showed:

- `authenticated` / `anon` have **no** `USAGE` on schema `app`
- No table `SELECT` for those roles on application tables

That is useful defense-in-depth, but **does not prove** Data API exposure settings. PostgREST exposure is a Dashboard / API-config surface independent of current table grants. Temporary RLS test GRANTs would widen risk **if** `app` were already exposed.

**Therefore:** Data API status remains operator-verified only.

---

## Current status

| Check | Result |
|-------|--------|
| Programmatic Dashboard read | Not available in this session |
| Operator evidence | **Verified** — operator reply `DATA_API_VERIFIED: app not exposed` (saved + refreshed) |
| `app` exposure | **Not exposed** |
| Automatic new-table exposure | **Disabled** (operator-confirmed) |
| Settings modified by agents | **No** |

Transactional RLS `--execute` was authorized and completed under Part 5C; see  
`PHASE_3C_PART5C_TRANSACTIONAL_RLS_EXECUTION_REPORT.md`.

---

## After operator confirmation

Reply with one of:

- `DATA_API_VERIFIED: app not exposed`
- `DATA_API_FINDING: app is exposed` (do **not** proceed with temporary GRANTs until remediated)

Update this document’s status field when evidence arrives.
