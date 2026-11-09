# CryptoNova — 70A End-to-End Test Matrix

| Area | What was run | Result | Blocked? |
| --- | --- | --- | --- |
| Revision planning, duplicate material skip, no backdated availability | `tests/test_core_70a_audit.py` | Passed in the 44-test run | No |
| Durable in-memory budget across a new instance, hourly cap, release, daily cap | same | Passed | Live Postgres ledger blocked until `0011` |
| Fail-closed budget does not call the provider | same | Passed | No |
| SQLite budget ledger rejected; missing table fail-closed | same | Passed | No |
| 69D structured output, injection, parity, no paid call | `tests/test_core_llm_69d.py` | Passed in the 44-test run | Durable Postgres budget not exercised |
| 69B alert dedup, telegram mock, scheduler off, API gate | `tests/test_core_news_69b.py` | Passed in the 44-test run | `0008` not applied, so live alert persistence is blocked |
| 69A classification and collection rules | `tests/test_core_news_69a.py` | Passed | Live provider calls not part of this run |
| 69E point-in-time exclusion and shadow isolation | `tests/test_core_backtest_69e.py` | Passed | Development news history still incomplete |
| Paper broker, 68A backtest, 69A.1 Postgres integration, 69C | Not re-run in this audit pass | Last full 68/69 run before these edits: 94 passed, 1 skipped | The skip is `NEWS_PG_INTEGRATION` unset |
| Browser `/news`, `/llm`, `/backtesting`, `/analytics`, `/paper`, `/agents` | Opened unsigned on the already running Next server | Each page redirects to sign-in | Signed-in records unverified. Running API returns 404 for news, LLM, and shadow-status |

Combined command for this audit:

```
uv run pytest tests/test_core_70a_audit.py tests/test_core_llm_69d.py tests/test_core_news_69b.py tests/test_core_news_69a.py tests/test_core_backtest_69e.py -q
→ 44 passed, 0 failed, 0 skipped
```

Tests that would claim a live Supabase alert, LLM audit, revision archive, or budget ledger are not treated as passed. Those tables are not on the development database.
