# CryptoNova 76 — Future Cutover Plan

This is a plan only. Phase 76 did not execute any step below. Security remediation stays deferred and remains a blocker to production and to live trading.

## Sequence that still requires a separate approval

1. Verify the development project identity is `wmirifmgaftassgrfbyl` and that the connection is the intended session pooler.
2. Verify the migration file checksum is still `79d1197e675da8dd8dc057670af762a23e385ddcb1bcaf26db6b66c0a4cb11d5`. If the file changed, stop and review the new digest.
3. Verify a fresh recoverable backup. The older CSV recovery copy predates revision `20261108_0011`. Managed point-in-time recovery was not verified in this phase.
4. Obtain an explicit operator approval that names the development project and revision `20261108_0012`.
5. Apply migration `20261108_0012` through the existing Alembic guard. Do not point Alembic at localhost and do not weaken `CRYPTONOVA_ALLOW_DEV_MIGRATIONS`.
6. Verify the six journal tables, the owner and fill constraints, forced RLS, and revision `20261108_0012`.
7. Run isolated development PostgreSQL parity tests. Do not treat the localhost results in `CRYPTONOVA_76_BACKTEST_PARITY.md` as this step.
8. Run isolated paper accounting tests without mixing them into the three existing paper sessions.
9. Run signal restart recovery against development only after a separate decision to persist signal rows.
10. Validate authenticated dashboards with a real signed-in session. Do not simulate authorization with the privileged role.
11. Obtain a second, separate approval for runtime cutover.
12. Switch the backtest runtime off SQLite only after development parity passes.
13. Verify a PostgreSQL failure does not silently fall back to SQLite. The current `journal_mode="postgres"` path already fails closed, and that guard must remain until the approved switch.
14. Perform a final acceptance review. Security remediation is still required before any production or live-trading claim.

## Current blockers to record with the plan

- Development password rotation is deferred.
- Least-privilege roles and grants are deferred. The privileged role bypasses RLS.
- Migration `0012` is not applied.
- Backtest runtime is still SQLite.
- Paper PostgreSQL runtime is not wired.
- Development signal restart recovery is unverified.
- Signed-in dashboards are unverified.
- Historical news provenance is incomplete, so historical news backtests stay invalid.
- `AGENT_ALLOW_LIVE` stays false.
