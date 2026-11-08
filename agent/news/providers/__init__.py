"""News providers — fixture, optional RSS, optional NewsData.io."""

from agent.news.providers.fixture import FixtureNewsProvider
from agent.news.providers.rss import RssNewsProvider

__all__ = ["FixtureNewsProvider", "RssNewsProvider"]
