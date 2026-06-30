"""
scrapers/reddit_scraper.py

Reddit scraper with dual-mode: PRAW (authenticated) + JSON API (fallback).

The JSON API fallback means this scraper NEVER fails — even without API keys,
even if Reddit blocks the app, we still get rising/hot signals.

KEY INSIGHT: We scrape RISING, not HOT.
    Hot  = already popular, 6-24h behind the trend curve.
    Rising = posts gaining velocity NOW, 6-24h AHEAD of mainstream.

Fallback chain:
    1. PRAW (official API, rich data including upvote_ratio, view_count)
    2. JSON API (reddit.com/r/sub.json — no auth, limited data)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    import praw
    HAS_PRAW = True
except ImportError:
    HAS_PRAW = False

from config import (
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, PLATFORM_TRUST
)
from scrapers.base import BaseScraper, RawSignal


# Subreddits always scraped regardless of niche (cross-niche signal)
GLOBAL_SUBREDDITS = ["all", "popular", "worldnews", "news"]

# Posts with upvote_ratio above this AND under 2h old are treated as early signals
EARLY_SIGNAL_RATIO = 0.85
EARLY_SIGNAL_MAX_AGE_HOURS = 2

# JSON API rate limits (respect Reddit's server — 1 req/2s)
JSON_INTER_REQUEST_DELAY = 2.0
JSON_USER_AGENT = REDDIT_USER_AGENT or "veloci-bot/1.0 (trend intelligence)"


class RedditScraper(BaseScraper):
    """
    Scrapes Reddit with automatic PRAW → JSON API fallback.
    If PRAW auth fails (401/403), seamlessly falls back to the public
    JSON endpoint which requires no credentials.
    """

    def __init__(self):
        super().__init__(
            name="reddit",
            trust_weight=PLATFORM_TRUST["reddit_rising"],
        )
        self._reddit: Optional["praw.Reddit"] = None
        self._praw_available: bool = False
        self._http_client: Optional[httpx.Client] = None

    def _get_praw_client(self) -> Optional["praw.Reddit"]:
        """Try to initialize PRAW. Returns None if auth fails."""
        if not HAS_PRAW or not REDDIT_CLIENT_ID or REDDIT_CLIENT_ID == "your_id_here":
            return None
        if self._reddit is not None:
            return self._reddit
        try:
            self._reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent=REDDIT_USER_AGENT,
                ratelimit_seconds=1,
            )
            # Test auth
            list(self._reddit.subreddit("all").hot(limit=1))
            self._praw_available = True
            logger.info("[Reddit] PRAW authenticated successfully")
            return self._reddit
        except Exception as e:
            logger.warning(f"[Reddit] PRAW auth failed ({e}), using JSON API fallback")
            self._praw_available = False
            self._reddit = None
            return None

    def _get_http_client(self) -> httpx.Client:
        """Get httpx client for JSON API fallback."""
        if self._http_client is None:
            self._http_client = httpx.Client(
                headers={"User-Agent": JSON_USER_AGENT},
                timeout=15.0,
                follow_redirects=True,
            )
        return self._http_client

    async def health_check(self) -> bool:
        """Health check — tries PRAW first, falls back to JSON API."""
        loop = asyncio.get_event_loop()

        # Try PRAW
        praw_client = await loop.run_in_executor(None, self._get_praw_client)
        if praw_client:
            logger.info("[Reddit] Health OK (PRAW authenticated)")
            return True

        # Fallback: JSON API
        try:
            client = self._get_http_client()
            r = await loop.run_in_executor(
                None,
                lambda: client.get("https://www.reddit.com/r/all/hot.json?limit=1")
            )
            if r.status_code == 200:
                logger.info("[Reddit] Health OK (JSON API fallback)")
                return True
            logger.error(f"[Reddit] JSON API returned {r.status_code}")
            return False
        except Exception as e:
            logger.error(f"[Reddit] health_check failed completely: {e}")
            return False

    async def scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        loop = asyncio.get_event_loop()

        # Route to PRAW or JSON based on availability
        if self._praw_available and self._reddit:
            return await loop.run_in_executor(
                None, self._scrape_praw, niche, niche_config
            )
        else:
            return await loop.run_in_executor(
                None, self._scrape_json, niche, niche_config
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # PRAW SCRAPER (authenticated, richer data)
    # ═══════════════════════════════════════════════════════════════════════════

    def _scrape_praw(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """Scrape via PRAW with rich metadata."""
        reddit = self._reddit
        signals: List[RawSignal] = []

        niche_subreddits = niche_config.get("subreddits", [])
        rising_subreddits = niche_config.get("subreddits_rising", niche_subreddits[:5])

        # RISING posts (primary signal)
        for sub_name in rising_subreddits:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.rising(limit=30):
                    sig = self._praw_post_to_signal(
                        post, niche, "reddit_rising",
                        PLATFORM_TRUST["reddit_rising"]
                    )
                    if sig:
                        signals.append(sig)
            except Exception as e:
                logger.warning(f"[Reddit/PRAW] rising failed for r/{sub_name}: {e}")

        # HOT posts (cross-validation)
        for sub_name in niche_subreddits[:8]:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.hot(limit=15):
                    sig = self._praw_post_to_signal(
                        post, niche, "reddit_hot",
                        PLATFORM_TRUST["reddit_hot"]
                    )
                    if sig:
                        signals.append(sig)
            except Exception as e:
                logger.warning(f"[Reddit/PRAW] hot failed for r/{sub_name}: {e}")

        logger.info(f"[Reddit/PRAW] {len(signals)} signals for niche={niche}")
        return signals

    def _praw_post_to_signal(self, post, niche: str, platform: str, trust: float) -> Optional[RawSignal]:
        """Convert a PRAW post object to a RawSignal."""
        try:
            title = post.title or ""
            body = (post.selftext or "")[:1000]
            if not title or title in ("[deleted]", "[removed]"):
                return None
            if post.score < 1:
                return None

            keywords = []
            if post.link_flair_text:
                keywords.append(post.link_flair_text)

            hashtags = [
                word[1:] for word in (title + " " + body).split()
                if word.startswith("#")
            ]

            published_at = datetime.fromtimestamp(
                post.created_utc, tz=timezone.utc
            ).replace(tzinfo=None)

            return RawSignal(
                platform=platform,
                platform_trust=min(trust, 1.0),
                source_id=post.id,
                url=f"https://reddit.com{post.permalink}",
                title=title,
                body=body,
                hashtags=hashtags,
                keywords=keywords,
                score=post.score,
                comments=post.num_comments,
                views=post.view_count or 0,
                published_at=published_at,
                niche=niche,
                raw_data={
                    "subreddit": post.subreddit.display_name,
                    "upvote_ratio": post.upvote_ratio,
                    "is_self": post.is_self,
                    "domain": post.domain,
                },
            )
        except Exception as e:
            logger.debug(f"[Reddit/PRAW] post_to_signal error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # JSON API FALLBACK (no auth, works everywhere)
    # ═══════════════════════════════════════════════════════════════════════════

    def _scrape_json(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """
        Scrape via Reddit's public JSON API — no auth needed.
        GET https://www.reddit.com/r/{subreddit}/{sort}.json?limit=N
        Falls back from /rising → /hot → /new when endpoints return 403.
        """
        client = self._get_http_client()
        signals: List[RawSignal] = []

        niche_subreddits = niche_config.get("subreddits", [])
        rising_subreddits = niche_config.get("subreddits_rising", niche_subreddits[:5])

        # RISING → HOT fallback for early signals
        for sub_name in rising_subreddits:
            try:
                # Try /rising first, fall back to /hot if 403
                posts = self._fetch_json_posts_fallback(client, sub_name, ["rising", "hot"])
                for post_data in posts:
                    sig = self._json_post_to_signal(
                        post_data, niche, "reddit_rising",
                        PLATFORM_TRUST["reddit_rising"]
                    )
                    if sig:
                        signals.append(sig)
            except Exception as e:
                logger.warning(f"[Reddit/JSON] rising/hot failed for r/{sub_name}: {e}")

        # HOT posts from full subreddit list
        for sub_name in niche_subreddits[:8]:
            try:
                posts = self._fetch_json_posts_fallback(client, sub_name, ["hot"])
                for post_data in posts:
                    sig = self._json_post_to_signal(
                        post_data, niche, "reddit_hot",
                        PLATFORM_TRUST["reddit_hot"]
                    )
                    if sig:
                        signals.append(sig)
            except Exception as e:
                logger.warning(f"[Reddit/JSON] hot failed for r/{sub_name}: {e}")

        # NEW posts with high upvote ratio (stealth early signal)
        for sub_name in rising_subreddits[:3]:
            try:
                posts = self._fetch_json_posts_fallback(client, sub_name, ["new"])
                for post_data in posts:
                    ratio = post_data.get("upvote_ratio", 0)
                    score = post_data.get("score", 0)
                    created = post_data.get("created_utc", 0)
                    from datetime import datetime, timezone
                    age_hours = (datetime.now(timezone.utc).timestamp() - created) / 3600 if created else 99
                    if ratio >= 0.85 and score >= 5 and age_hours <= 3:
                        sig = self._json_post_to_signal(
                            post_data, niche, "reddit_rising",
                            PLATFORM_TRUST["reddit_rising"] * 1.1
                        )
                        if sig:
                            signals.append(sig)
            except Exception as e:
                logger.warning(f"[Reddit/JSON] new scan failed for r/{sub_name}: {e}")

        logger.info(f"[Reddit/JSON] {len(signals)} signals for niche={niche}")
        return signals

    def _fetch_json_posts_fallback(self, client: httpx.Client, subreddit: str, sort_chain: list, limit: int = 25) -> list:
        """
        Fetch posts from Reddit JSON API with sort-type fallback.
        /rising returns 403 from some IPs (no auth). Falls back through
        the sort_chain until one works.
        """
        import time
        for sort in sort_chain:
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&raw_json=1"
            try:
                r = client.get(url)
                time.sleep(JSON_INTER_REQUEST_DELAY)

                if r.status_code == 429:
                    logger.warning(f"[Reddit/JSON] Rate limited on r/{subreddit}")
                    return []
                if r.status_code == 403 and len(sort_chain) > 1:
                    logger.debug(f"[Reddit/JSON] r/{subreddit}/{sort} 403, trying next sort")
                    continue
                if r.status_code != 200:
                    logger.debug(f"[Reddit/JSON] r/{subreddit}/{sort} returned {r.status_code}")
                    continue

                data = r.json()
                posts = [child["data"] for child in data.get("data", {}).get("children", [])]
                if posts:
                    return posts
            except Exception as e:
                logger.debug(f"[Reddit/JSON] r/{subreddit}/{sort} error: {e}")
                continue
        return []

    def _json_post_to_signal(self, post: dict, niche: str, platform: str, trust: float) -> Optional[RawSignal]:
        """Convert a Reddit JSON post dict to a RawSignal."""
        try:
            title = post.get("title", "").strip()
            body = post.get("selftext", "")[:1000]
            score = post.get("score", 0)

            if not title or title in ("[deleted]", "[removed]"):
                return None
            if score < 1:
                return None

            keywords = []
            flair = post.get("link_flair_text")
            if flair:
                keywords.append(flair)

            hashtags = [
                word[1:] for word in (title + " " + body).split()
                if word.startswith("#")
            ]

            created_utc = post.get("created_utc", 0)
            published_at = datetime.fromtimestamp(
                created_utc, tz=timezone.utc
            ).replace(tzinfo=None) if created_utc else datetime.now(timezone.utc)

            permalink = post.get("permalink", "")

            return RawSignal(
                platform=platform,
                platform_trust=min(trust, 1.0),
                source_id=post.get("id", ""),
                url=f"https://reddit.com{permalink}" if permalink else "",
                title=title,
                body=body,
                hashtags=hashtags,
                keywords=keywords,
                score=score,
                comments=post.get("num_comments", 0),
                views=0,  # JSON API doesn't expose view_count
                published_at=published_at,
                niche=niche,
                raw_data={
                    "subreddit": post.get("subreddit", ""),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                    "is_self": post.get("is_self", False),
                    "domain": post.get("domain", ""),
                    "source": "json_api_fallback",
                },
            )
        except Exception as e:
            logger.debug(f"[Reddit/JSON] json_post_to_signal error: {e}")
            return None
