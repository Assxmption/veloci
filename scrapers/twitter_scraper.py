"""
scrapers/twitter_scraper.py

Twitter/X scraper with multi-tier fallback:

Tier 1: Tweepy API v2 (if bearer token has credits)
Tier 2: RSS proxy via Nitter instances (free, no auth)
Tier 3: Google News search for Twitter-sourced stories

Free tier reality (as of 2024):
  - Free: 1 app, 1,500 tweets/month WRITE, NO read search
  - Basic ($100/mo): 10K tweets/month read, 50K/month full archive
  - We need read access → use fallback tiers when API fails

Velocity detection:
  Compare mention count in LAST 1H vs LAST 3H.
  10x more mentions in last hour = EXPLODING trend.
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from datetime import timezone
from typing import List, Optional

import httpx
import feedparser
from loguru import logger

try:
    import tweepy
    HAS_TWEEPY = True
except ImportError:
    HAS_TWEEPY = False

from config import TWITTER_BEARER_TOKEN, PLATFORM_TRUST, TWITTER_MAX_RESULTS
from scrapers.base import BaseScraper, RawSignal


# Nitter RSS instances — these expose Twitter data as RSS feeds
# They rotate; we try multiple until one works
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
    "https://nitter.1d4.us",
]

# Trending topics page patterns
TWITTER_TRENDING_RSS = [
    "https://trends24.in/feed/",             # Trending topics RSS
    "https://getdaytrends.com/feed/",         # Another trending source
]


class TwitterScraper(BaseScraper):
    """
    Multi-tier Twitter scraper:
    1. Tweepy v2 API (if credits available)
    2. Nitter RSS fallback (free, no auth)
    3. Google News Twitter filter (last resort)
    """

    def __init__(self):
        super().__init__(
            name="twitter_velocity",
            trust_weight=PLATFORM_TRUST["twitter_velocity"],
        )
        self._tweepy_client: Optional["tweepy.Client"] = None
        self._tweepy_available: bool = False
        self._http_client: Optional[httpx.Client] = None
        self._working_nitter: Optional[str] = None

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=15.0,
                follow_redirects=True,
            )
        return self._http_client

    def _try_tweepy(self) -> bool:
        """
        Attempt to use Tweepy. Returns True if API has credits.
        Returns False on 402 (no credits) or any auth error.
        """
        if not HAS_TWEEPY or not TWITTER_BEARER_TOKEN:
            return False
        try:
            client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN, wait_on_rate_limit=False)
            client.search_recent_tweets(query="test", max_results=10)
            self._tweepy_client = client
            self._tweepy_available = True
            logger.info("[Twitter] Tweepy API available with credits")
            return True
        except Exception as e:
            err_str = str(e)
            if "402" in err_str or "Payment Required" in err_str:
                logger.info("[Twitter] Tweepy 402 — no credits, using fallback scrapers")
            else:
                logger.warning(f"[Twitter] Tweepy failed: {e}")
            self._tweepy_available = False
            return False

    async def health_check(self) -> bool:
        """
        Health check — tries Tweepy first, then Nitter RSS, then Google News.
        Returns True if ANY tier works.
        """
        loop = asyncio.get_event_loop()

        # Tier 1: Tweepy
        tweepy_ok = await loop.run_in_executor(None, self._try_tweepy)
        if tweepy_ok:
            return True

        # Tier 2: Nitter RSS
        nitter_ok = await loop.run_in_executor(None, self._probe_nitter)
        if nitter_ok:
            logger.info(f"[Twitter] Nitter RSS available at {self._working_nitter}")
            return True

        # Tier 3: Google News filter
        gnews_ok = await loop.run_in_executor(None, self._probe_google_news)
        if gnews_ok:
            logger.info("[Twitter] Falling back to Google News Twitter filter")
            return True

        logger.warning("[Twitter] All tiers failed — scraper unavailable this cycle")
        return False

    def _probe_nitter(self) -> bool:
        """Find a working Nitter instance."""
        client = self._get_http_client()
        for instance in NITTER_INSTANCES:
            try:
                # Try fetching a popular account's RSS
                r = client.get(f"{instance}/elikinosho/rss", timeout=10)
                if r.status_code == 200 and "<rss" in r.text[:500]:
                    self._working_nitter = instance
                    return True
            except Exception:
                continue
        return False

    def _probe_google_news(self) -> bool:
        """Check if Google News RSS is accessible."""
        client = self._get_http_client()
        try:
            r = client.get(
                "https://news.google.com/rss/search?q=trending+twitter&hl=en-US&gl=US&ceid=US:en",
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    async def scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        loop = asyncio.get_event_loop()

        # Tier 1: Tweepy API
        if self._tweepy_available and self._tweepy_client:
            return await loop.run_in_executor(
                None, self._scrape_tweepy, niche, niche_config
            )

        # Tier 2: Nitter RSS
        if self._working_nitter:
            return await loop.run_in_executor(
                None, self._scrape_nitter, niche, niche_config
            )

        # Tier 3: Google News Twitter filter
        return await loop.run_in_executor(
            None, self._scrape_google_news_twitter, niche, niche_config
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 1: TWEEPY API (if credits available)
    # ═══════════════════════════════════════════════════════════════════════════

    def _scrape_tweepy(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """Original Tweepy-based scraping."""
        client = self._tweepy_client
        signals: List[RawSignal] = []
        twitter_queries = niche_config.get("twitter_queries", [])
        seed_keywords = niche_config.get("seed_keywords", [])
        all_queries = list(set(twitter_queries[:4] + seed_keywords[:2]))

        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        three_hours_ago = now - timedelta(hours=3)

        for query_term in all_queries[:5]:
            try:
                full_query = (
                    f"{query_term} lang:en -is:retweet "
                    f"(has:hashtags OR has:links) "
                    f"min_faves:5"
                )
                response = client.search_recent_tweets(
                    query=full_query,
                    max_results=min(TWITTER_MAX_RESULTS, 100),
                    tweet_fields=[
                        "created_at", "public_metrics", "entities",
                        "lang", "text", "author_id",
                    ],
                    start_time=three_hours_ago,
                    sort_order="recency",
                )
                if not response.data:
                    continue

                tweets = response.data
                recent_tweets = [
                    t for t in tweets
                    if t.created_at and t.created_at >= one_hour_ago
                ]
                velocity_ratio = len(recent_tweets) / max(len(tweets) - len(recent_tweets), 1)

                for tweet in tweets:
                    sig = self._tweepy_to_signal(tweet, niche, query_term, velocity_ratio)
                    if sig:
                        signals.append(sig)

            except Exception as e:
                if "429" in str(e) or "TooManyRequests" in str(e):
                    logger.warning(f"[Twitter/Tweepy] rate limited on '{query_term}'")
                    break
                logger.warning(f"[Twitter/Tweepy] failed '{query_term}': {e}")

        logger.info(f"[Twitter/Tweepy] {len(signals)} signals for niche={niche}")
        return signals

    def _tweepy_to_signal(self, tweet, niche: str, query_term: str, velocity_ratio: float) -> Optional[RawSignal]:
        try:
            text = tweet.text or ""
            if not text:
                return None
            metrics = tweet.public_metrics or {}
            hashtags = []
            entities = getattr(tweet, "entities", {}) or {}
            if "hashtags" in entities:
                hashtags = [h.get("tag", "") for h in entities["hashtags"]]

            published_at = None
            if tweet.created_at:
                published_at = tweet.created_at.replace(tzinfo=None)

            return RawSignal(
                platform="twitter_velocity",
                platform_trust=min(self.trust_weight * (1 + velocity_ratio * 0.2), 1.0),
                source_id=str(tweet.id),
                url=f"https://twitter.com/i/web/status/{tweet.id}",
                title=text[:280],
                body="",
                hashtags=hashtags,
                keywords=[query_term],
                score=metrics.get("like_count", 0),
                comments=metrics.get("reply_count", 0),
                shares=metrics.get("retweet_count", 0),
                views=metrics.get("impression_count", 0),
                published_at=published_at,
                niche=niche,
                raw_data={"query_term": query_term, "velocity_ratio": velocity_ratio, "source": "tweepy_api"},
            )
        except Exception as e:
            logger.debug(f"[Twitter/Tweepy] to_signal error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 2: NITTER RSS (free, no auth)
    # ═══════════════════════════════════════════════════════════════════════════

    def _scrape_nitter(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """
        Scrape Twitter via Nitter RSS feeds.
        Nitter exposes /search/rss?q=keyword for public search results.
        """
        client = self._get_http_client()
        signals: List[RawSignal] = []
        seed_keywords = niche_config.get("seed_keywords", [])
        twitter_queries = niche_config.get("twitter_queries", [])
        all_queries = list(set(twitter_queries[:3] + seed_keywords[:3]))

        for query in all_queries[:5]:
            try:
                url = f"{self._working_nitter}/search/rss?f=tweets&q={query}"
                r = client.get(url, timeout=15)
                if r.status_code != 200:
                    continue

                feed = feedparser.parse(r.text)
                for entry in feed.entries[:20]:
                    sig = self._rss_entry_to_signal(entry, niche, query, "nitter_rss")
                    if sig:
                        signals.append(sig)

            except Exception as e:
                logger.warning(f"[Twitter/Nitter] failed query='{query}': {e}")

        logger.info(f"[Twitter/Nitter] {len(signals)} signals for niche={niche}")
        return signals

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER 3: GOOGLE NEWS TWITTER FILTER (last resort — gets trending topics)
    # ═══════════════════════════════════════════════════════════════════════════

    def _scrape_google_news_twitter(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """
        Use Google News RSS to find stories about what's trending on Twitter/X.
        Not real Twitter data, but captures the SAME trend signals.
        """
        client = self._get_http_client()
        signals: List[RawSignal] = []
        seed_keywords = niche_config.get("seed_keywords", [])

        # Search Google News for "[keyword] trending twitter" or "viral"
        queries = [
            f"{kw} trending" for kw in seed_keywords[:4]
        ] + [
            f"{kw} viral" for kw in seed_keywords[:2]
        ]

        for query in queries[:5]:
            try:
                url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
                r = client.get(url, timeout=15)
                if r.status_code != 200:
                    continue

                feed = feedparser.parse(r.text)
                for entry in feed.entries[:10]:
                    sig = self._rss_entry_to_signal(entry, niche, query, "gnews_twitter")
                    if sig:
                        signals.append(sig)

            except Exception as e:
                logger.warning(f"[Twitter/GNews] failed query='{query}': {e}")

        logger.info(f"[Twitter/GNews] {len(signals)} signals for niche={niche}")
        return signals

    def _rss_entry_to_signal(
        self, entry, niche: str, query: str, source: str
    ) -> Optional[RawSignal]:
        """Convert an RSS feed entry to a RawSignal."""
        try:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")[:500]

            if not title:
                return None

            # Parse published date
            published_at = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    from time import mktime
                    published_at = datetime.fromtimestamp(mktime(entry.published_parsed))
                except Exception:
                    pass

            # Extract hashtags from title + summary
            text = title + " " + summary
            hashtags = re.findall(r"#(\w+)", text)

            return RawSignal(
                platform="twitter_velocity",
                platform_trust=self.trust_weight * 0.8,  # Slight penalty for indirect source
                source_id=f"{source}_{hash(link) % 10**8}",
                url=link,
                title=title,
                body=summary,
                hashtags=hashtags,
                keywords=[query],
                score=50,  # Default score for RSS entries
                niche=niche,
                published_at=published_at,
                raw_data={
                    "query": query,
                    "source": source,
                    "feed_source": getattr(entry, "source", {}).get("title", ""),
                },
            )
        except Exception as e:
            logger.debug(f"[Twitter/RSS] entry_to_signal error: {e}")
            return None
