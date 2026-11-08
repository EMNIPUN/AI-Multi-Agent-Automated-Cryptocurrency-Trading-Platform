"""Minimal public RSS provider using stdlib XML + httpx (no feedparser dependency)."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from agent.news.schemas import RawArticle


class RssNewsProvider:
    """
    Fetches approved RSS/Atom URLs only.

    Many free crypto RSS feeds are delayed relative to wire events —
    ``is_delayed_feed`` defaults True unless caller marks otherwise.
    """

    provider_id = "rss_public"
    is_delayed_feed = True

    def __init__(
        self,
        feed_urls: list[str] | tuple[str, ...],
        *,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
        delayed: bool = True,
    ) -> None:
        self._urls = tuple(feed_urls)
        self._timeout = timeout
        self._client = client
        self.is_delayed_feed = delayed

    def fetch(self, *, now_ms: int) -> list[RawArticle]:
        out: list[RawArticle] = []
        owns = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout, headers={"Accept": "application/rss+xml, application/xml, text/xml"})
        try:
            for url in self._urls:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"}:
                    continue
                t0 = time.monotonic()
                try:
                    res = client.get(url)
                    res.raise_for_status()
                    latency = int((time.monotonic() - t0) * 1000)
                    out.extend(
                        self._parse_feed(
                            res.text,
                            feed_url=url,
                            now_ms=now_ms,
                            latency_ms=latency,
                        )
                    )
                except (httpx.HTTPError, ET.ParseError, ValueError):
                    continue
        finally:
            if owns:
                client.close()
        return out

    def _parse_feed(
        self,
        xml_text: str,
        *,
        feed_url: str,
        now_ms: int,
        latency_ms: int,
    ) -> list[RawArticle]:
        root = ET.fromstring(xml_text)
        # RSS 2.0
        items = root.findall(".//item")
        if items:
            out_rss: list[RawArticle] = []
            for item in items:
                art = self._from_rss_item(
                    item, feed_url=feed_url, now_ms=now_ms, latency_ms=latency_ms
                )
                if art:
                    out_rss.append(art)
            return out_rss
        # Atom
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(
            ".//a:entry", ns
        )
        out: list[RawArticle] = []
        for entry in entries:
            art = self._from_atom_entry(entry, feed_url=feed_url, now_ms=now_ms, latency_ms=latency_ms)
            if art:
                out.append(art)
        return out

    def _from_rss_item(
        self,
        item: ET.Element,
        *,
        feed_url: str,
        now_ms: int,
        latency_ms: int,
    ) -> RawArticle | None:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            return None
        desc = (item.findtext("description") or "").strip()
        pub = item.findtext("pubDate")
        published_ms = _parse_date_ms(pub)
        guid = (item.findtext("guid") or link).strip()
        host = urlparse(feed_url).netloc or "rss"
        return RawArticle(
            provider_id=self.provider_id,
            external_id=guid,
            title=title,
            url=link,
            source_name=host,
            published_at_ms=published_ms,
            observed_at_ms=now_ms,
            summary=desc[:2000],
            body_excerpt=desc[:4000],
            provider_latency_ms=latency_ms,
            is_delayed_feed=self.is_delayed_feed,
            raw={"feed_url": feed_url},
        )

    def _from_atom_entry(
        self,
        entry: ET.Element,
        *,
        feed_url: str,
        now_ms: int,
        latency_ms: int,
    ) -> RawArticle | None:
        def _text(tag: str) -> str:
            node = entry.find(tag) or entry.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
            return (node.text or "").strip() if node is not None else ""

        title = _text("title")
        link = ""
        for child in entry:
            if child.tag.endswith("link"):
                href = child.attrib.get("href") or ""
                if href:
                    link = href
                    break
        if not title or not link:
            return None
        summary = _text("summary") or _text("content")
        published_ms = _parse_date_ms(_text("published") or _text("updated"))
        eid = _text("id") or link
        host = urlparse(feed_url).netloc or "atom"
        return RawArticle(
            provider_id=self.provider_id,
            external_id=eid,
            title=title,
            url=link,
            source_name=host,
            published_at_ms=published_ms,
            observed_at_ms=now_ms,
            summary=summary[:2000],
            body_excerpt=summary[:4000],
            provider_latency_ms=latency_ms,
            is_delayed_feed=self.is_delayed_feed,
            raw={"feed_url": feed_url},
        )


def _parse_date_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    # ISO-8601 fallback
    try:
        from datetime import datetime

        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return None
