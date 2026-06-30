"""
scrapers/news_scraper.py

Multi-source news aggregator. Three layers:

  Layer 1 — RSS Feeds (zero auth, zero cost, real-time)
    Major publications push RSS within minutes of publishing.
    This is often faster than any social platform for breaking news.
    We track: BBC, Reuters, NYT, AP, plus niche-specific outlets.

  Layer 2 — NewsAPI (100 req/day free tier)
    Structured access to 80,000+ news sources with search by keyword.
    Use for keyword-specific signal and cross-validation.

  Layer 3 — GDELT (Global Database of Events, Language, and Tone)
    Free, no key, near-real-time global event database.
    Covers 100+ languages, 250+ countries.
    Best for: geopolitical events, cultural moments, protest/crisis signals
    that will become trending content 24-48h later.

Breaking news on RSS/GDELT = 12-48h lead time on social platform trends.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional
import email.utils

import aiohttp
import feedparser
from newsapi import NewsApiClient
from loguru import logger

from config import NEWS_API_KEY, GLOBAL_RSS_FEEDS, PLATFORM_TRUST
from scrapers.base import BaseScraper, RawSignal


# GDELT GKG (Global Knowledge Graph) — free, updated every 15 min
GDELT_GKG_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query={query}&mode=artlist&maxrecords=25&format=json"
    "&timespan=360"  # Last 6 hours
    "&sort=ToneDesc"  # Most positive (shareable) first
)

GDELT_THEMES_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query=sourcelang:english&mode=artlist"
    "&maxrecords=50&format=json&timespan=120"
)


class NewsScraper(BaseScraper):
    """
    Aggregates signals from RSS feeds, NewsAPI, and GDELT.
    """

    def __init__(self):
        super().__init__(
            name="news_rss",
            trust_weight=PLATFORM_TRUST["news_rss"],
        )
        self._newsapi: Optional[NewsApiClient] = None

    def _get_newsapi(self) -> Optional[NewsApiClient]:
        if not NEWS_API_KEY:
            return None
        if self._newsapi is None:
            self._newsapi = NewsApiClient(api_key=NEWS_API_KEY)
        return self._newsapi

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    GLOBAL_RSS_FEEDS[0], timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"[News] health_check failed: {e}")
            return False

    async def scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        rss_feeds = GLOBAL_RSS_FEEDS + niche_config.get("rss_feeds", [])
        seed_keywords = niche_config.get("seed_keywords", [])

        # Run all three layers concurrently
        rss_task      = self._scrape_rss(niche, rss_feeds)
        newsapi_task  = self._scrape_newsapi(niche, seed_keywords[:3])
        gdelt_task    = self._scrape_gdelt(niche, seed_keywords[:2])

        results = await asyncio.gather(
            rss_task, newsapi_task, gdelt_task, return_exceptions=True
        )

        signals: List[RawSignal] = []
        for result in results:
            if isinstance(result, list):
                signals.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"[News] layer failed: {result}")

        logger.info(f"[News] {len(signals)} total signals for niche={niche}")
        return signals

    async def _scrape_rss(self, niche: str, feeds: List[str]) -> List[RawSignal]:
        """Parse RSS/Atom feeds concurrently."""
        signals: List[RawSignal] = []

        async def fetch_feed(url: str) -> List[RawSignal]:
            feed_signals = []
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=10),
                        headers={"User-Agent": "Mozilla/5.0 (compatible; veloci-bot/1.0)"},
                    ) as resp:
                        content = await resp.text(errors="replace")

                parsed = feedparser.parse(content)
                for entry in parsed.entries[:15]:
                    sig = self._rss_entry_to_signal(entry, niche, url)
                    if sig:
                        feed_signals.append(sig)
            except Exception as e:
                logger.debug(f"[RSS] fetch failed url={url}: {e}")
            return feed_signals

        tasks = [fetch_feed(url) for url in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                signals.extend(result)

        return signals

    def _rss_entry_to_signal(
        self, entry, niche: str, feed_url: str
    ) -> Optional[RawSignal]:
        try:
            title = getattr(entry, "title", "").strip()
            if not title:
                return None

            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")
            tags = [t.get("term", "") for t in getattr(entry, "tags", [])]

            # Parse published date
            published_at = None
            if hasattr(entry, "published"):
                try:
                    parsed = email.utils.parsedate_to_datetime(entry.published)
                    published_at = parsed.replace(tzinfo=None)
                except Exception:
                    pass
            if published_at is None and hasattr(entry, "updated_parsed"):
                if entry.updated_parsed:
                    published_at = datetime(*entry.updated_parsed[:6])

            return RawSignal(
                platform="news_rss",
                platform_trust=PLATFORM_TRUST["news_rss"],
                source_id=f"rss_{hash(link) % 999999}",
                url=link or feed_url,
                title=title,
                body=summary[:800],
                keywords=tags[:5],
                score=0,  # RSS has no engagement data
                published_at=published_at,
                niche=niche,
                raw_data={"feed_url": feed_url, "author": getattr(entry, "author", "")},
            )
        except Exception as e:
            logger.debug(f"[RSS] _rss_entry_to_signal error: {e}")
            return None

    async def _scrape_newsapi(
        self, niche: str, keywords: List[str]
    ) -> List[RawSignal]:
        """Query NewsAPI for keyword-specific recent articles."""
        newsapi = self._get_newsapi()
        if not newsapi:
            return []

        signals: List[RawSignal] = []
        loop = asyncio.get_event_loop()

        for kw in keywords[:2]:  # Budget-aware: 2 calls max
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda k=kw: newsapi.get_everything(
                        q=k,
                        language="en",
                        sort_by="publishedAt",  # Freshest first
                        page_size=20,
                        from_param=None,  # Last 24h default
                    )
                )
                for article in response.get("articles", []):
                    sig = self._newsapi_article_to_signal(article, niche, kw)
                    if sig:
                        signals.append(sig)
            except Exception as e:
                logger.warning(f"[NewsAPI] failed kw='{kw}': {e}")

        return signals

    def _newsapi_article_to_signal(
        self, article: dict, niche: str, keyword: str
    ) -> Optional[RawSignal]:
        try:
            title = article.get("title", "").strip()
            if not title or title == "[Removed]":
                return None

            published_str = article.get("publishedAt", "")
            published_at = None
            if published_str:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)

            return RawSignal(
                platform="news_api",
                platform_trust=PLATFORM_TRUST["news_api"],
                source_id=f"newsapi_{hash(article.get('url','')) % 999999}",
                url=article.get("url", ""),
                title=title,
                body=(article.get("description") or "")[:500],
                keywords=[keyword],
                score=0,
                published_at=published_at,
                niche=niche,
                raw_data={
                    "source": article.get("source", {}).get("name", ""),
                    "author": article.get("author", ""),
                    "keyword": keyword,
                },
            )
        except Exception as e:
            logger.debug(f"[NewsAPI] article_to_signal error: {e}")
            return None

    async def _scrape_gdelt(
        self, niche: str, keywords: List[str]
    ) -> List[RawSignal]:
        """
        Query GDELT for global events matching niche keywords.
        GDELT updates every 15 minutes and covers global news in real-time.
        Free, no auth, no rate limit (be polite with delays).
        """
        signals: List[RawSignal] = []

        async with aiohttp.ClientSession() as session:
            for kw in keywords[:2]:
                try:
                    url = GDELT_GKG_URL.format(
                        query=kw.replace(" ", "%20")
                    )
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=15),
                        headers={"User-Agent": "veloci-bot/1.0"},
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json(content_type=None)

                    articles = data.get("articles", [])
                    for article in articles[:10]:
                        sig = self._gdelt_article_to_signal(article, niche, kw)
                        if sig:
                            signals.append(sig)

                    await asyncio.sleep(1.5)  # Polite delay

                except Exception as e:
                    logger.debug(f"[GDELT] failed kw='{kw}': {e}")

        return signals

    def _gdelt_article_to_signal(
        self, article: dict, niche: str, keyword: str
    ) -> Optional[RawSignal]:
        try:
            title = article.get("title", "").strip()
            url = article.get("url", "")
            if not title or not url:
                return None

            published_str = article.get("seendate", "")
            published_at = None
            if published_str:
                try:
                    published_at = datetime.strptime(published_str, "%Y%m%dT%H%M%SZ")
                except Exception:
                    pass

            tone = float(article.get("tone", 0))

            return RawSignal(
                platform="gdelt",
                platform_trust=PLATFORM_TRUST["gdelt"],
                source_id=f"gdelt_{hash(url) % 999999}",
                url=url,
                title=title,
                body="",
                keywords=[keyword],
                score=max(0, int(tone * 10)),  # Positive tone → higher score
                published_at=published_at,
                niche=niche,
                raw_data={
                    "domain": article.get("domain", ""),
                    "language": article.get("language", ""),
                    "tone": tone,
                    "keyword": keyword,
                },
            )
        except Exception as e:
            logger.debug(f"[GDELT] article_to_signal error: {e}")
            return None
