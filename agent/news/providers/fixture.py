"""Deterministic offline fixture provider for tests and demos (no network)."""

from __future__ import annotations

from agent.news.schemas import RawArticle


class FixtureNewsProvider:
    provider_id = "fixture_offline"
    is_delayed_feed = False

    def __init__(self, articles: list[RawArticle] | None = None) -> None:
        self._articles = list(articles or [])

    def fetch(self, *, now_ms: int) -> list[RawArticle]:
        if self._articles:
            return list(self._articles)
        # Default deterministic sample set — not live market news.
        base = now_ms - 3_600_000
        return [
            RawArticle(
                provider_id=self.provider_id,
                external_id="fx_btc_hack_demo",
                title="Demo: Major exchange reports hot wallet security breach affecting Bitcoin withdrawals",
                url="https://example.invalid/news/demo-exchange-breach",
                source_name="CryptoNova Fixture",
                published_at_ms=base,
                observed_at_ms=base + 120_000,
                summary="Offline fixture describing a hypothetical exchange security incident for BTC.",
                body_excerpt="This is synthetic test content for Prompt 69A. Not a real event.",
                is_delayed_feed=False,
            ),
            RawArticle(
                provider_id=self.provider_id,
                external_id="fx_eth_etf_demo",
                title="Demo: Analyst notes Ethereum ETF inflows remain elevated this week",
                url="https://example.invalid/news/demo-eth-etf",
                source_name="CryptoNova Fixture",
                published_at_ms=base + 600_000,
                observed_at_ms=base + 700_000,
                summary="Offline fixture about ETH ETF flows — informational only.",
                body_excerpt="Synthetic informational article for classification tests.",
                is_delayed_feed=False,
            ),
            RawArticle(
                provider_id=self.provider_id,
                external_id="fx_dup_title",
                title="Demo: Major exchange reports hot wallet security breach affecting Bitcoin withdrawals",
                url="https://example.invalid/news/demo-exchange-breach-mirror",
                source_name="CryptoNova Fixture Mirror",
                published_at_ms=base,
                observed_at_ms=base + 180_000,
                summary="Duplicate title fixture for dedupe tests.",
                is_delayed_feed=False,
            ),
        ]
