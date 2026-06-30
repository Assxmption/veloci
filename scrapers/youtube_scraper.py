"""
scrapers/youtube_scraper.py

YouTube Data API v3 scraper.

Two signal types:
  1. Trending videos (chart=mostPopular) — per region, per category
     → tells us what's already breaking through
  2. Search results sorted by date for niche keywords
     → catches content before it hits trending
  3. YouTube search suggestions (autocomplete)
     → what people are actively typing RIGHT NOW (pure intent signal)

Free tier: 10,000 units/day
  - videos.list costs 1 unit
  - search.list costs 100 units
  - We use budget-aware fetching to stay under quota

Budget allocation:
  - Trending (3 regions × 3 categories): 3 * 3 = 9 search calls = 900 units
  - Search by keyword (3 terms × 2 calls): 6 * 100 = 600 units
  - Buffer: ~8,500 units remaining for rest of pipeline
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from datetime import timezone
from typing import List, Optional
import httpx

from googleapiclient.discovery import build
from loguru import logger

from config import YOUTUBE_API_KEY, PLATFORM_TRUST, YOUTUBE_TRENDING_REGIONS
from scrapers.base import BaseScraper, RawSignal


# YouTube category IDs relevant to most niches
CATEGORY_MAP = {
    "tech_ai":       ["28", "26"],   # Science & Tech, Howto
    "finance":       ["25", "22"],   # News, People & Blogs
    "entertainment": ["24", "10"],   # Entertainment, Music
    "lifestyle":     ["22", "26"],   # People & Blogs, Howto
}


class YoutubeScraper(BaseScraper):
    """
    Scrapes YouTube trending videos and keyword-based search results.
    Also queries the YouTube autocomplete endpoint for real-time intent signals.
    """

    def __init__(self):
        super().__init__(
            name="youtube_trending",
            trust_weight=PLATFORM_TRUST["youtube_trending"],
        )
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        return self._client

    async def health_check(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._get_client().videos().list(
                    part="id", chart="mostPopular", regionCode="US", maxResults=1
                ).execute()
            )
            return True
        except Exception as e:
            logger.error(f"[YouTube] health_check failed: {e}")
            return False

    async def scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        loop = asyncio.get_event_loop()
        signals = await loop.run_in_executor(
            None, self._scrape_sync, niche, niche_config
        )

        # Autocomplete is HTTP-only, run async
        autocomplete_signals = await self._scrape_autocomplete(niche, niche_config)
        return signals + autocomplete_signals

    def _scrape_sync(self, niche: str, niche_config: dict) -> List[RawSignal]:
        yt = self._get_client()
        signals: List[RawSignal] = []
        categories = CATEGORY_MAP.get(niche, ["24", "25"])
        regions = niche_config.get("youtube_region_codes", ["US", "IN"])[:3]
        search_terms = niche_config.get("youtube_search_terms", [])[:3]

        # ── TRENDING VIDEOS (chart=mostPopular) ────────────────────────────────
        for region in regions:
            for cat_id in categories[:2]:  # Limit categories to save quota
                try:
                    resp = yt.videos().list(
                        part="snippet,statistics,contentDetails",
                        chart="mostPopular",
                        regionCode=region,
                        videoCategoryId=cat_id,
                        maxResults=25,
                    ).execute()

                    for item in resp.get("items", []):
                        sig = self._item_to_signal(item, niche, region)
                        if sig:
                            signals.append(sig)
                except Exception as e:
                    logger.warning(f"[YouTube] trending failed region={region} cat={cat_id}: {e}")

        # ── KEYWORD SEARCH (sorted by date = freshest content) ─────────────────
        for term in search_terms:
            try:
                resp = yt.search().list(
                    part="snippet",
                    q=term,
                    type="video",
                    order="date",           # Date order = freshest first
                    maxResults=20,
                    publishedAfter="2025-01-01T00:00:00Z",  # Avoid ancient content
                ).execute()

                for item in resp.get("items", []):
                    sig = self._search_item_to_signal(item, niche, term)
                    if sig:
                        signals.append(sig)
            except Exception as e:
                logger.warning(f"[YouTube] search failed term='{term}': {e}")

        return signals

    async def _scrape_autocomplete(
        self, niche: str, niche_config: dict
    ) -> List[RawSignal]:
        """
        Query YouTube's autocomplete (suggest) API.
        This is an unofficial endpoint but has been stable for years.
        It returns what people are ACTIVELY TYPING — pure intent signal.
        No API key required.
        """
        signals: List[RawSignal] = []
        seed_keywords = niche_config.get("seed_keywords", [])[:5]

        async with httpx.AsyncClient(timeout=10.0) as client:
            for kw in seed_keywords:
                try:
                    resp = await client.get(
                        "https://suggestqueries.google.com/complete/search",
                        params={
                            "client": "youtube",
                            "ds": "yt",
                            "q": kw,
                            "hl": "en",
                        }
                    )
                    # Response format: [query, [[suggestion, 0, []], ...], ...]
                    import json
                    raw = json.loads(resp.text[resp.text.index("["):])
                    suggestions = [s[0] for s in raw[1]]

                    for suggestion in suggestions[:5]:
                        signals.append(RawSignal(
                            platform="youtube_autocomplete",
                            platform_trust=0.80,  # High trust — pure intent
                            source_id=f"autocomplete_{kw}_{suggestion[:20]}",
                            url="https://youtube.com/results?search_query=" + suggestion.replace(" ", "+"),
                            title=suggestion,
                            body=f"YouTube autocomplete for: {kw}",
                            keywords=[kw],
                            score=100,  # No engagement data, use placeholder
                            niche=niche,
                            published_at=datetime.now(timezone.utc),
                        ))
                except Exception as e:
                    logger.debug(f"[YouTube] autocomplete failed kw='{kw}': {e}")

        return signals

    def _item_to_signal(
        self, item: dict, niche: str, region: str
    ) -> Optional[RawSignal]:
        try:
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            title = snippet.get("title", "")
            if not title:
                return None

            tags = snippet.get("tags", []) or []
            published_str = snippet.get("publishedAt", "")
            published_at = None
            if published_str:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)

            return RawSignal(
                platform="youtube_trending",
                platform_trust=self.trust_weight,
                source_id=item["id"],
                url=f"https://youtube.com/watch?v={item['id']}",
                title=title,
                body=snippet.get("description", "")[:500],
                keywords=tags[:10],
                score=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                views=int(stats.get("viewCount", 0)),
                published_at=published_at,
                niche=niche,
                raw_data={
                    "channel": snippet.get("channelTitle"),
                    "region": region,
                    "category_id": snippet.get("categoryId"),
                    "duration": item.get("contentDetails", {}).get("duration"),
                },
            )
        except Exception as e:
            logger.debug(f"[YouTube] _item_to_signal error: {e}")
            return None

    def _search_item_to_signal(
        self, item: dict, niche: str, search_term: str
    ) -> Optional[RawSignal]:
        try:
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            title = snippet.get("title", "")
            if not title or not video_id:
                return None

            published_str = snippet.get("publishedAt", "")
            published_at = None
            if published_str:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)

            return RawSignal(
                platform="youtube_trending",
                platform_trust=self.trust_weight * 0.85,  # Slightly lower than chart
                source_id=video_id,
                url=f"https://youtube.com/watch?v={video_id}",
                title=title,
                body=snippet.get("description", "")[:500],
                keywords=[search_term],
                score=0,  # Search API doesn't return stats — needs second call
                published_at=published_at,
                niche=niche,
                raw_data={
                    "channel": snippet.get("channelTitle"),
                    "search_term": search_term,
                },
            )
        except Exception as e:
            logger.debug(f"[YouTube] _search_item_to_signal error: {e}")
            return None
