# CryptoNova — 70B Database Integration Tests

**Status: EXECUTED against development `wmirifmgaftassgrfbyl` after `20261108_0011`.**

Isolated owner and `70b1` identifiers. OpenAI and Telegram were not called. Deletable test rows were removed. Two append-only revisions for `70b1evt26a00b9fa389` remain because UPDATE and DELETE are rejected.

| Check | Result |
| --- | --- |
| Schema tables, RLS, uniques, alert foreign key, revision trigger, no `anon` grants | Pass |
| Existing news and paper counts preserved | Pass |
| News persist, duplicate article, restart read | Pass |
| First revision, duplicate skip, material second revision, as-of selection | Pass |
| Trigger rejects UPDATE and DELETE | Pass |
| Alert insert, duplicate suppression, acknowledgement, unconfirmed delivery | Pass |
| LLM audit save and idempotent replay, decision unchanged | Pass |
| Budget reservation, hourly concurrency, restart, release, unknown cost, daily cap | Pass |
| Unreachable budget storage makes no provider call | Pass |

The script printed 59 PASS lines and `failures=0`. No paid OpenAI call and no Telegram send were performed. The full pytest suite was not re-run in this pass.
