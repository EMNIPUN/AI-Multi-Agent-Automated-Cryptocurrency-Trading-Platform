# tests

Offline unit/integration tests (mocked exchange only).

Current coverage focuses on agent fail-closed position handling (Phase 1A).

```powershell
uv run pytest tests -q
# or: .\.venv\Scripts\python.exe -m pytest tests -q
```

Do not add tests that require live Bybit credentials or place orders.
