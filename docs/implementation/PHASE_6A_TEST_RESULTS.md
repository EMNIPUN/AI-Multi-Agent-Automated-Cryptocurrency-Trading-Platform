# Phase 6A — Test Results

## Python (mocked)

```text
pytest tests/test_phase6a_automation_foundation.py -q
18 passed
```

Coverage includes:

1. Default SIGNALS_ONLY  
2. Pipeline skip in SIGNALS_ONLY  
3. Duplicate order / intent prevention  
4. Daily loss halt  
5. Insufficient balance  
6. Stale data + spread veto  
7. Stop-loss required  
8. Spot/futures isolation (linear disabled)  
9. Mainnet mode locked  
10. Ambiguous timeout → reconciliation  
11. Gate blocks submission without ORDER_SUBMISSION_APPROVED  
12. Stop rejection → emergency halt  
13. Mock fill + protection verified  
14. Restart intent survival  
15. API status — no secrets; arm endpoint 403  
16. AGENT_ALLOW_LIVE not a shortcut  
17. Emergency procedure never assumes cancel  
18. Local durability without Supabase  

## Live Testnet orders

**Not executed.** Connectivity checklist prepared in gate summary — requires separate approval.

## Frontend

Automation status proxy + control panel (controls disabled). Run Vitest/typecheck with Studio changes as part of local verify.
