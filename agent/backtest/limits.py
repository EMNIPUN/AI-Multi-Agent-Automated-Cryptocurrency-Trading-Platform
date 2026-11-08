"""Conservative resource limits for controlled historical backtest runs (68C)."""

from __future__ import annotations

# Hard caps — overridable via ApiSettings / env for local operators.
DEFAULT_MAX_CANDLES_PER_RUN = 5_000
DEFAULT_MAX_RANGE_MS = 90 * 24 * 60 * 60 * 1000  # 90 days
DEFAULT_MAX_SIMULTANEOUS_RUNS = 1
DEFAULT_MAX_QUEUED_RUNS = 2
DEFAULT_MAX_RUNTIME_SECONDS = 600  # 10 minutes
DEFAULT_MAX_CACHED_DATASET_BYTES = 8 * 1024 * 1024  # 8 MiB per dataset file
DEFAULT_MAX_CACHE_TOTAL_BYTES = 256 * 1024 * 1024  # 256 MiB cache budget
DEFAULT_MAX_REPORT_BYTES = 8 * 1024 * 1024  # mirrors 68B reader cap
DEFAULT_MAX_RETAINED_ARTIFACTS = 50
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0
DEFAULT_HTTP_MAX_RETRIES = 3
DEFAULT_HTTP_MIN_INTERVAL_SECONDS = 0.12
DEFAULT_PAGE_LIMIT = 1000  # Bybit V5 max

# UI / API allowlists (subset of engine-supported intervals).
RUN_UI_INTERVALS = frozenset({"15", "60", "240"})
RUN_UI_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})
RUN_UI_MARKET_TYPES = frozenset({"spot", "linear"})
RUN_UI_RISK_MODES = frozenset({"signal_only", "portfolio"})
RUN_UI_DATA_SOURCES = frozenset({"bybit_public", "offline_fixture"})
