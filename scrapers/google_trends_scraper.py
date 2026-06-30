"""
scrapers/google_trends_scraper.py

Google Trends via pytrends (no API key needed).

Why this matters more than all the others:
  Google Trends RISING queries = searches that have grown 5000%+
  vs their baseline in the last 24h. This is the single most reliable
  predictor of social media trends. When people Google something,
  they're about to look for content about it on TikTok, Reels, YouTube.

  We capture two types:
    1. Real-time trending searches (hourly, US + India focus)
    2. Related rising queries for niche seed keywords

  Both types are 12-48h upstream of the social media trend peak.

Rate limiting: pytrends is unofficial. We use generous delays to avoid
  getting blocked (429). The scheduler handles retry logic.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from datetime import timezone
from typing import List

from pytrends.request import TrendReq
from loguru import logger

from config import (
    GOOGLE_TRENDS_GEO, GOOGLE_TRENDS_TIMEFRAME,
    GOOGLE_TRENDS_CATEGORIES, PLATFORM_TRUST
)
from scrapers.base import BaseScraper, RawSignal


TRENDING_GEOS = [
    ("", "worldwide"),
    ("US", "united_states"),
    ("IN", "india"),
    ("GB", "united_kingdom"),
]

INTER_REQUEST_DELAY = 2.5  # seconds — be respectful, avoid 429


class GoogleTrendsScraper(BaseScraper):
    """
    Captures rising search queries from Google Trends.
    No API key required — uses pytrends unofficial client.
    """

    def __init__(self):
        super().__init__(
            name="google_trends_rising",
            trust_weight=PLATFORM_TRUST["google_trends_rising"],
        )

    def _get_client(self) -> TrendReq:
        """
        Create pytrends client WITHOUT retries/backoff_factor.
        These params cause urllib3 Retry(method_whitelist=...) errors
        in newer urllib3 versions. We handle retries ourselves.
        """
        return TrendReq(
            hl="en-US",
            tz=0,  # UTC
            timeout=(10, 30),
            # Do NOT pass retries= or backoff_factor= here.
            # urllib3 2.x renamed method_whitelist → allowed_methods
            # and pytrends 4.x doesn't handle this correctly.
        )

    async def health_check(self) -> bool:
        """
        Health check using related_queries (not trending_searches which Google killed).
        Also tests suggestions endpoint as a secondary probe.
        """
        try:
            loop = asyncio.get_event_loop()
            pt = self._get_client()
            # Test related_queries — our workhorse method
            def _probe():
                pt.build_payload(kw_list=["test"], timeframe="today 1-m", geo="")
                return pt.related_queries()
            result = await loop.run_in_executor(None, _probe)
            return isinstance(result, dict)
        except Exception as e:
            logger.error(f"[GoogleTrends] health_check failed: {e}")
            return False

    async def scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._scrape_sync, niche, niche_config
        )

    def _scrape_sync(self, niche: str, niche_config: dict) -> List[RawSignal]:
        pt = self._get_client()
        signals: List[RawSignal] = []
        seed_keywords = niche_config.get("seed_keywords", [])

        # ── AUTOCOMPLETE SUGGESTIONS (real-time search intent) ──────────────
        # Google Autocomplete = what people are typing RIGHT NOW.
        # This is a pure intent signal — upstream of all social trends.
        for kw in seed_keywords[:6]:
            try:
                sug_list = pt.suggestions(kw)
                time.sleep(INTER_REQUEST_DELAY)

                for sug in sug_list:
                    title = sug.get("title", "").strip()
                    sug_type = sug.get("type", "")
                    if not title or title.lower() == kw.lower():
                        continue
                    signals.append(RawSignal(
                        platform="google_trends_rising",
                        platform_trust=self.trust_weight,
                        source_id=f"gsuggest_{kw[:10]}_{title[:20]}",
                        url=f"https://trends.google.com/trends/explore?q={title.replace(' ', '+')}",
                        title=title,
                        body=f"Google Autocomplete for '{kw}' — type: {sug_type}",
                        keywords=[kw, title],
                        score=80,  # Suggestions = moderate signal strength
                        niche=niche,
                        published_at=datetime.now(timezone.utc),
                        raw_data={
                            "seed_keyword": kw,
                            "suggestion_type": sug_type,
                            "type": "autocomplete_suggestion",
                        },
                    ))
            except Exception as e:
                logger.warning(f"[GoogleTrends] suggestions failed kw={kw}: {e}")

        # ── RELATED RISING QUERIES (the real gold) ─────────────────────────────
        # For each seed keyword, get "rising" related queries.
        # Rising = queries with 5000%+ growth — these are THE early signal.
        for i in range(0, len(seed_keywords[:10]), 5):
            batch = seed_keywords[i:i+5]
            try:
                pt.build_payload(
                    kw_list=batch,
                    timeframe=GOOGLE_TRENDS_TIMEFRAME,
                    geo=GOOGLE_TRENDS_GEO,
                )
                time.sleep(INTER_REQUEST_DELAY)

                related = pt.related_queries()
                for kw, data in related.items():
                    if not isinstance(data, dict):
                        continue
                    rising_df = data.get("rising")
                    if rising_df is None or rising_df.empty:
                        continue

                    for _, row in rising_df.iterrows():
                        query = str(row.get("query", "")).strip()
                        value = int(row.get("value", 0))
                        if not query:
                            continue

                        signals.append(RawSignal(
                            platform="google_trends_rising",
                            platform_trust=self.trust_weight,
                            source_id=f"grelated_{kw[:10]}_{query[:25]}",
                            url=f"https://trends.google.com/trends/explore?q={query.replace(' ', '+')}",
                            title=query,
                            body=f"Rising related query for '{kw}' — value: {value}",
                            keywords=[kw, query],
                            score=min(value, 9999),  # Google caps at Breakout (9999)
                            niche=niche,
                            published_at=datetime.now(timezone.utc),
                            raw_data={
                                "seed_keyword": kw,
                                "value": value,
                                "is_breakout": value >= 5000,
                                "type": "related_rising",
                            },
                        ))

                time.sleep(INTER_REQUEST_DELAY)

            except Exception as e:
                logger.warning(f"[GoogleTrends] related_rising failed batch={batch}: {e}")

        # ── INTEREST OVER TIME spike detection ─────────────────────────────────
        # Check for sudden spikes in interest for niche keywords
        try:
            top_seeds = seed_keywords[:3]
            if top_seeds:
                pt.build_payload(
                    kw_list=top_seeds,
                    timeframe="now 7-d",  # Last 7 days for spike detection
                    geo="US",
                )
                time.sleep(INTER_REQUEST_DELAY)
                iot = pt.interest_over_time()

                if not iot.empty:
                    for kw in top_seeds:
                        if kw not in iot.columns:
                            continue
                        series = iot[kw]
                        if len(series) < 2:
                            continue
                        # Spike = last value is 50%+ above the 7-day average
                        avg = series[:-1].mean()
                        last = series.iloc[-1]
                        if avg > 0 and (last / avg) >= 1.5:
                            signals.append(RawSignal(
                                platform="google_trends_rising",
                                platform_trust=self.trust_weight * 1.1,  # Bonus — spike confirmed
                                source_id=f"gspike_{kw[:20]}",
                                url=f"https://trends.google.com/trends/explore?q={kw.replace(' ', '+')}",
                                title=f"Search spike: {kw}",
                                body=f"Interest spike detected: {last:.0f} vs avg {avg:.0f} (7-day). Ratio: {last/avg:.2f}x",
                                keywords=[kw],
                                score=int(last),
                                niche=niche,
                                published_at=datetime.now(timezone.utc),
                                raw_data={
                                    "keyword": kw,
                                    "last_value": float(last),
                                    "avg_value": float(avg),
                                    "spike_ratio": float(last / avg),
                                    "type": "interest_spike",
                                },
                            ))
        except Exception as e:
            logger.warning(f"[GoogleTrends] interest_over_time failed: {e}")

        logger.info(f"[GoogleTrends] {len(signals)} signals for niche={niche}")
        return signals
