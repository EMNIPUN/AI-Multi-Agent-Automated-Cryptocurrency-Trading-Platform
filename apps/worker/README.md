# apps/worker

Future long-running **worker** process(es) for agent loops, coordinators, and background jobs.

Today the automated loop still starts via root `run_agent.py`. Migration into this app should preserve dry-run defaults and mainnet live locks.
