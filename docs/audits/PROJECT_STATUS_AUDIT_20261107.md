# CryptoNova — Full Project Status Audit

| Field | Value |
| --- | --- |
| Audit date | 2026-11-07 |
| Method | Live env/DB/SQLite inspection + implementation gate docs + Gate B execution evidence |
| Secrets | Not reproduced |
| Cloud writes / orders during audit | None |

**Note:** `CURRENT_REPOSITORY_AUDIT.md` (2026-11-04) is **STALE** for platform scope (it predates FastAPI/Next/Phase 3–6A/4D). Prefer this document for current status.

---

## 1. Executive verdict

CryptoNova is a **local-first personal trading intelligence platform** with:

- Working **signals-only** multi-agent engine + SQLite durability + optional auto candle evaluation  
- Working **Next.js Agent Studio / markets UI** + FastAPI backend + Supabase Auth foundation  
- **Supabase schema migrated through Phase 4D Gate B** (`20261107_0004`) — cloud signal **tables empty**, writes/sync still **OFF**  
- **Phase 6A mocked execution foundation** only — no live Testnet/Mainnet order submission authorized  

**Overall readiness**

| Question | Answer |
| --- | --- |
| Safe for unattended mainnet automation? | **No** |
| Safe for personal signals-only research (local)? | **Yes, with gates left OFF** |
| Supabase long-term signal mirror ready to use? | **Schema yes · activation no** (Gate C+) |
| Exchange binding persistence / private catalog? | **Designed · persistence OFF · Auth E2E residual** |
| Production SaaS / multi-tenant? | **Not ready** |

---

## 2. Architecture (current)

```text
apps/web (Next.js 15) ──proxy──► apps/api (FastAPI)
                                      │
                                      ├─ public Bybit market REST/WS
                                      ├─ SignalPipeline + auto engine ──► SQLite (SoT)
                                      ├─ Supabase Auth JWT verify
                                      └─ SQLAlchemy ──► Supabase Postgres (privileged role)
agent/ + bot/ ── legacy CLI trader / rule agent (still present)
```

| Layer | Responsibility | Authority today |
| --- | --- | --- |
| Local SQLite `multi_agent_signals.sqlite3` | Signals, paper risk, scheduler, outbox | **Operational SoT** |
| Supabase `app.*` | Catalog + bindings schema + empty 4D signal tables | Mirror schema only |
| Phase 6A `automation_execution.sqlite3` | Mocked execution intents | Local mocked only |

---

## 3. Phase scoreboard

| Phase | Scope | Status |
| --- | --- | --- |
| 0–1 | Repo hygiene, position/order/risk/candle safety | Implemented (legacy + foundation) |
| 2 | FastAPI health/system, Auth/JWKS foundation | Implemented |
| 3C | Ownership, RLS design, bindings API, credential hardening | **Partial** — offline PASS; Auth E2E / least-privilege DB role residual |
| 3D / 3D.1 | Public market data + WS stream | **PASS** |
| 4A | Multi-agent signals (Market/Trend/Momentum/Coordinator/Risk) | **PASS** · strategy `4B.1.0` |
| 4B | Local SQLite signal history + paper risk | **PASS** |
| 4C | Automatic confirmed-candle engine `4C.1.0` | **PASS** (signals only) |
| 4D Gate A | Local cloud payload/atomic outbox/sync worker/JWT APIs | **COMPLETE** (local) |
| 4D Gate B | Supabase DDL `20261107_0004` | **MIGRATION VERIFIED** |
| 4D Gate C | Cloud signal writes | **NOT STARTED** · REQUIRES APPROVAL |
| 4D Gate D | Automatic cloud sync + owner binding | **NOT STARTED** |
| 4D Gate E | SQLite → Supabase import | **NOT STARTED** |
| 4D Gate F / 6A live | Exchange orders | **DISABLED** · 6A mocked foundation only |

---

## 4. Live configuration snapshot (redacted)

| Setting | Effective |
| --- | --- |
| Project ref | `wmirifmgaftassgrfbyl` |
| Region host | `aws-0-ap-southeast-2.pooler.supabase.com` |
| `CRYPTONOVA_DB_TARGET` | `development` |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | `false` |
| Signal Supabase writes / operator / sync | unset → **false** |
| `SIGNAL_CLOUD_OWNER_USER_ID` | unset (sync would fail-closed) |
| Binding persistence gates | unset → **false** |
| `PRIVATE_DATA_READS_ENABLED` | **false** |
| `AGENT_ALLOW_LIVE` | **false** |
| `AGENT_DRY_RUN` | **true** |
| `LLM_AGENTS_ENABLED` | **false** |
| Order submission / perpetual auto | unset → **false** |
| `BYBIT_TESTNET` | **false** (Mainnet API host selection — wallet/CLI risk surface; signal engine uses public data) |

---

## 5. Database state

### Alembic

Active revisions include `20261104_0001` … **`20261107_0004`**.  
Remote `app.alembic_version` = **`20261107_0004`**.

### Remote `app` tables

`agent_decisions`, `system_events`, `strategy_configs`, `exchange_account_bindings`,  
`signal_history`, `signal_agent_contributions`, `signal_risk_events`,  
`scheduler_evaluation_history`, `scheduler_audit`, `alembic_version`

Phase 4D signal/scheduler tables: **exist, row counts 0**.

### Local SQLite

| Metric | Value |
| --- | --- |
| Schema | v4 · integrity ok |
| signal_history | 3 |
| paper_risk_state | 1 |
| outbox / checkpoints | 0 |
| Backup | `data/backups/multi_agent_signals_20261107_202853.sqlite3` |

---

## 6. Security posture

| Topic | Status |
| --- | --- |
| JWT verification (JWKS/HS256 code paths) | Implemented |
| Owner filters on cloud repos/APIs | Implemented |
| RLS SELECT-own on new 4D tables | Applied |
| App `DATABASE_URL` privilege | **BYPASSRLS residual** — filters mandatory |
| Least-privilege runtime DB role | **Not deployed** |
| Browser secrets | Server-side DB/exchange secrets; public anon URL/key only on web |
| Cloud write / sync / import | Fail-closed OFF |
| Exchange binding persistence | OFF |
| Live trading / Testnet place_order | OFF |
| Supabase managed backups (Free) | Unavailable — residual risk accepted for Gate B DDL |

---

## 7. Trading / execution isolation

| Path | State |
| --- | --- |
| SignalPipeline → orders | Not connected |
| Auto engine | Signals only; refuses if `AGENT_ALLOW_LIVE` |
| Phase 6A | Mocked adapter; place_order gated |
| CLI `main.py` / `run_agent.py` | Still present; dry-run default; live requires explicit flags |
| Operator Mainnet wallet reads | Preserved separately; not signal path |

---

## 8. Frontend / product surfaces

- Next.js Agent Studio (signals, automation panel, replay/observability)  
- Markets public data UI + stream  
- Auth login/signup UI  
- Exchange binding settings UI (fixture / persistence off)  
- Cloud history APIs exist JWT-bound but cloud rows empty until Gate C  

---

## 9. Test evidence (recent, not re-run this audit hour)

| Suite | Last recorded |
| --- | --- |
| Phase 4A–4D + 6A pytest | 82 passed (Gate B prep) |
| Vitest | 32 passed |
| TypeScript | passed |
| Gate B remote catalog verify | PASS after apply |

---

## 10. Top risks & gaps

1. **Privileged Postgres role** for FastAPI (BYPASSRLS).  
2. **Free-tier no managed backups** — recovery depends on SQLite + residual acceptance.  
3. **Gate C–E not done** — cloud history unused; outbox empty vs 3 local signals (backfill later).  
4. **Auth E2E / binding persistence** still gated from 3C scoreboard.  
5. **`BYBIT_TESTNET=false`** — ensure CLI/wallet keys are intentional Mainnet-read only; never enable live agent flags casually.  
6. **Root README / CURRENT_REPOSITORY_AUDIT** partially outdated vs multi-app reality.  
7. **Large uncommitted/doc surface** — operational git hygiene not audited this pass.

---

## 11. Recommended next steps (ordered)

1. **Do nothing on Gate C** until you explicitly want cloud signal writes.  
2. Before Gate C: set/verify `SIGNAL_CLOUD_OWNER_USER_ID` from real Auth JWT `sub`; keep sync OFF initially.  
3. Plan least-privilege DB role (remove app BYPASSRLS reliance).  
4. Refresh root README to match CryptoNova multi-app status.  
5. Keep SQLite backups on a schedule; consider Supabase plan upgrade if cloud data becomes valuable.  
6. Phase 6A Testnet orders only under a separate, explicit approval package.

---

## 12. Bottom line

**Gate B DDL is done and verified.** The platform is a **signals-first local research system** with a prepared but inactive Supabase mirror. **No cloud signal activation and no exchange order submission** are in force. Treat Gates C–F as separate controlled approvals.
