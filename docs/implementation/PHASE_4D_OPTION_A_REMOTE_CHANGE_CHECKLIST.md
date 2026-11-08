# Phase 4D Option A — Remote Security-Change Checklist

**Status:** Awaiting separate explicit operator approval.  
**Target:** Supabase project `wmirifmgaftassgrfbyl` only.  
**This checklist is not authorization to execute.**

---

## A. Required approval text (operator)

> I authorize Option A **remote security-change** for CryptoNova development project `wmirifmgaftassgrfbyl` only.  
> Scope: create least-privilege roles/grants/policies per `PHASE_4D_OPTION_A_SECURITY_MIGRATION_PLAN.md` / pending revision `20261108_0005`.  
> I understand rollback of roles/grants may be incomplete via Alembic alone.  
> Cloud writes, sync, import, and exchange orders remain OFF.  
> Runtime credential cutover is **[included | separate approval]**.

---

## B. Pre-change

- [ ] Confirm project ref `wmirifmgaftassgrfbyl` / region `ap-southeast-2`
- [ ] Confirm Alembic `20261107_0004`
- [ ] Run `uv run python scripts/_option_a_readonly_rls_inventory.py`
- [ ] Run `uv run python scripts/_gate_c1_readonly_catalog.py`
- [ ] Confirm all write/sync/order/migration flags OFF
- [ ] Record table owners, policies, role attributes
- [ ] Confirm Free-plan / Supabase role creation is feasible
- [ ] Prepare LOGIN passwords offline (not in git)

## C. Apply (only after approval)

- [ ] Move/copy pending revision into active `alembic/versions` **or** run reviewed SQL in SQL editor as documented
- [ ] Enable `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` only for window if using Alembic
- [ ] Apply revision `20261108_0005`
- [ ] Immediately disable migration allow flag
- [ ] Verify roles: `rolbypassrls=false`, not superuser
- [ ] Verify policies exist for `cryptonova_api_runtime`
- [ ] Verify grants match matrix (no DELETE for runtime)
- [ ] Verify no unexpected grants on `auth`/`storage`

## D. Optional credential cutover (separate if required)

- [ ] Set runtime connection URL to LOGIN runtime role
- [ ] Point Alembic at migrator URL
- [ ] Enable `RUNTIME_DB_IDENTITY_ENABLED` only after smoke test
- [ ] Restart API / dispose pools
- [ ] Verify `current_user` is runtime role
- [ ] Verify foreign-owner SELECT denied
- [ ] Verify own-owner SELECT allowed (with test row only if separately approved)

## E. Abort conditions

- Wrong project / region
- Cannot create NOBYPASSRLS role
- Policies fail to attach to runtime role
- Accidental data DML
- Application cannot start after cutover
- Any exchange/order flag flipped

## F. Rollback / recovery

- [ ] Switch API back to previous credential if cutover failed
- [ ] REVOKE runtime grants / DROP runtime policies if needed
- [ ] DROP LOGIN role then base role only after dependency check
- [ ] Do not FORCE DROP without audit
- [ ] Re-run RO inventory; compare to pre-change snapshot

## G. Post-change validation

- [ ] `uv run pytest tests/test_option_a_least_privilege_security.py tests/test_phase4d_gate_c1_security.py -q`
- [ ] Confirm cloud writes/sync/orders still OFF
- [ ] Document evidence in a new Gate report
- [ ] Only then consider Gate C2 under Option B residual no longer needed for DB role

## H. Safety confirmation (must remain true)

- Supabase cloud writes: OFF  
- Cloud sync: OFF  
- Historical import: OFF  
- Exchange orders: OFF  
- No deployment required for this security change  
