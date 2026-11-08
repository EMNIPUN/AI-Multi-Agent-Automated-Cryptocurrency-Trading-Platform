"""Public Bybit V5 market-data constants (no secrets)."""

from __future__ import annotations

BYBIT_PUBLIC_REST_BASE = "https://api.bybit.com"
BYBIT_PUBLIC_WS_SPOT = "wss://stream.bybit.com/v5/public/spot"
BYBIT_PUBLIC_WS_LINEAR = "wss://stream.bybit.com/v5/public/linear"

# Personal-use watchlist defaults; overridable via query / env.
DEFAULT_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

MARKET_CATEGORIES: tuple[str, ...] = ("spot", "linear")

# Bybit V5 kline intervals used by the dashboard.
SUPPORTED_INTERVALS: tuple[str, ...] = ("1", "5", "15", "60", "240", "D")

INTERVAL_LABELS: dict[str, str] = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "60": "1h",
    "240": "4h",
    "D": "1D",
}

# Soft client-side awareness (Bybit public REST is generous; stay polite).
REST_MIN_INTERVAL_SECONDS = 0.05
WS_PING_INTERVAL_SECONDS = 20.0
WS_STALE_AFTER_SECONDS = 45.0
WS_RECONNECT_BASE_SECONDS = 0.5
WS_RECONNECT_MAX_SECONDS = 30.0
ORDERBOOK_DEPTH_DEFAULT = 50
KLINE_LIMIT_DEFAULT = 200
KLINE_LIMIT_MAX = 1000
TRADES_LIMIT_DEFAULT = 50
TRADES_LIMIT_MAX = 1000

# Data path labels — never conflate with private live account connectivity.
DATA_PATH_PUBLIC_LIVE = "public_live"
DATA_PATH_PUBLIC_SIMULATED = "public_simulated"
DATA_PATH_SAMPLE = "sample"
DATA_PATH_REPLAY = "replay"
