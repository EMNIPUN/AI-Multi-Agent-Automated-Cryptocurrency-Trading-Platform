"""Market News Intelligence (Prompt 69A foundation).

Advisory-only. Does not place trades or alter SignalPipeline decisions.
"""

from agent.news.config import NEWS_SCHEMA_VERSION, NewsConfig
from agent.news.service import NewsIntelligenceService

__all__ = ["NEWS_SCHEMA_VERSION", "NewsConfig", "NewsIntelligenceService"]
