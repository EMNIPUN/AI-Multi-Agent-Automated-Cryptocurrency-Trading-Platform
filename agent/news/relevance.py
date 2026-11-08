"""Asset relevance heuristics from title/summary text."""

from __future__ import annotations

import re

_ASSET_PATTERNS: dict[str, tuple[str, ...]] = {
    "BTCUSDT": (r"\bbtc\b", r"\bbitcoin\b", r"\bxbt\b"),
    "ETHUSDT": (r"\beth\b", r"\bethereum\b"),
    "SOLUSDT": (r"\bsol\b", r"\bsolana\b"),
}


def infer_assets(text: str, *, monitored: tuple[str, ...] | None = None) -> tuple[str, ...]:
    blob = (text or "").lower()
    wanted = monitored or tuple(_ASSET_PATTERNS.keys())
    hits: list[str] = []
    for symbol in wanted:
        patterns = _ASSET_PATTERNS.get(symbol, ())
        if any(re.search(p, blob) for p in patterns):
            hits.append(symbol)
    return tuple(hits)


def is_crypto_relevant(text: str) -> bool:
    blob = (text or "").lower()
    keys = (
        "crypto",
        "bitcoin",
        "ethereum",
        "blockchain",
        "exchange",
        "defi",
        "stablecoin",
        "token",
        "btc",
        "eth",
        "solana",
    )
    return any(k in blob for k in keys)
