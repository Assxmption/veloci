"""
pipeline/aggregator.py

The aggregator orchestrates all 8 scrapers in parallel,
deduplicates signals, and feeds the NLP pipeline.

Run order per cycle:
  1. Launch all scrapers concurrently (asyncio.gather)
  2. Collect RawSignal lists from each scraper
  3. Deduplicate by URL / content hash
  4. Filter signals too old to be relevant
  5. Feed to NLPProcessor → TrendCluster list
  6. Feed to TrendRanker → ranked TrendCluster list
  7. Persist to DB, return results

Handles scraper failures gracefully — if TikTok's browser
crashes, the other 7 scrapers continue unaffected.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from loguru import logger

from config import NICHES, TREND_HISTORY_HOURS
from scrapers.base import RawSignal
from scrapers.reddit_scraper import RedditScraper
from scrapers.youtube_scraper import YoutubeScraper
from scrapers.google_trends_scraper import GoogleTrendsScraper
from scrapers.twitter_scraper import TwitterScraper
from scrapers.news_scraper import NewsScraper
from scrapers.instagram_scraper import InstagramScraper
from pipeline.nlp_processor import NLPProcessor, TrendCluster
from pipeline.ranker import TrendRanker
from pipeline.rate_limiter import (
    check_rate_limit, report_success, report_failure, get_all_status
)


# Maximum age of signals to include in clustering
MAX_SIGNAL_AGE_HOURS = 24


class TrendAggregator:
    """
    Master aggregator. Call run_cycle(niche) to get ranked trends.
    """

    def __init__(self):
        # Instantiate scrapers once — they maintain client connections
        self.scrapers = {
            "reddit":        RedditScraper(),
            "youtube":       YoutubeScraper(),
            "google_trends": GoogleTrendsScraper(),
            "twitter":       TwitterScraper(),
            "news":          NewsScraper(),
            "instagram":     InstagramScraper(),
        }
        self.nlp = NLPProcessor()
        self.ranker = TrendRanker()

        # Cache for novelty comparison
        self._recent_embeddings: List = []
        self._previous_clusters: List[TrendCluster] = []

    async def run_cycle(
        self, niche: str
    ) -> List[TrendCluster]:
        """
        Full scrape → NLP → rank cycle for one niche.

        Args:
            niche: Key from config.NICHES

        Returns:
            Ranked list of TrendCluster objects
        """
        if niche not in NICHES:
            raise ValueError(f"Unknown niche: {niche}. Valid: {list(NICHES.keys())}")

        niche_config = NICHES[niche]
        logger.info(f"[Aggregator] Starting cycle for niche={niche}")
        start = datetime.now(timezone.utc)

        # 1. Scrape all platforms concurrently
        all_signals = await self._scrape_all(niche, niche_config)
        logger.info(f"[Aggregator] {len(all_signals)} raw signals collected")

        # 2. Deduplicate
        signals = self._deduplicate(all_signals)
        logger.info(f"[Aggregator] {len(signals)} signals after dedup")

        # 3. Filter by age
        signals = self._filter_by_age(signals)
        logger.info(f"[Aggregator] {len(signals)} signals after age filter")

        if not signals:
            logger.warning(f"[Aggregator] No valid signals for niche={niche}")
            return []

        # 4. Cap signals to prevent NLP embedding timeout on large batches
        #    Keep top signals by engagement (score + comments), ensuring
        #    platform diversity by not over-representing any one source.
        MAX_NLP_BATCH = 200
        if len(signals) > MAX_NLP_BATCH:
            import collections
            by_platform = collections.defaultdict(list)
            for s in signals:
                by_platform[s.platform].append(s)
            
            for p in by_platform:
                by_platform[p].sort(key=lambda s: (s.score + s.comments), reverse=True)
                
            selected = []
            idx = 0
            while len(selected) < MAX_NLP_BATCH:
                added_any = False
                for p in by_platform:
                    if idx < len(by_platform[p]):
                        selected.append(by_platform[p][idx])
                        added_any = True
                        if len(selected) == MAX_NLP_BATCH:
                            break
                if not added_any:
                    break
                idx += 1
                
            signals = selected
            logger.info(
                f"[Aggregator] Capped to {len(signals)} top signals "
                f"via round-robin platform selection"
            )

        # 4. NLP: embed, cluster, extract keywords
        clusters = self.nlp.process(
            signals,
            existing_embeddings=self._recent_embeddings,
        )

        # 5. Rank
        ranked = self.ranker.rank(
            clusters,
            historical_clusters=self._previous_clusters,
        )

        # 6. Update caches
        self._previous_clusters = ranked
        self._recent_embeddings = [
            c.centroid_embedding for c in ranked
            if c.centroid_embedding is not None
        ]

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info(
            f"[Aggregator] Cycle complete for niche={niche} in {elapsed:.1f}s. "
            f"{len(ranked)} trends ranked."
        )
        return ranked

    async def run_all_niches(self) -> dict:
        """
        Run cycles for all configured niches concurrently.

        Returns:
            Dict mapping niche → list of ranked TrendClusters
        """
        tasks = {
            niche: self.run_cycle(niche)
            for niche in NICHES.keys()
        }
        results = {}
        for niche, task in tasks.items():
            try:
                results[niche] = await task
            except Exception as e:
                logger.error(f"[Aggregator] Cycle failed for niche={niche}: {e}")
                results[niche] = []
        return results

    async def _scrape_all(
        self, niche: str, niche_config: dict
    ) -> List[RawSignal]:
        """
        Launch all scrapers concurrently with rate limiting + circuit breakers.
        Each scraper checks its token bucket before firing.
        Circuit breakers trip after 3 consecutive failures → 5-min cooldown.
        """
        async def _guarded_scrape(name: str, scraper):
            """Rate-limited, circuit-breaker-guarded scrape."""
            allowed = await check_rate_limit(name)
            if not allowed:
                logger.info(f"[Aggregator] {name}: rate-limited or circuit open — skipping")
                return []
            try:
                signals = await scraper.safe_scrape(niche, niche_config)
                report_success(name)
                return signals
            except Exception as e:
                report_failure(name)
                logger.warning(f"[Aggregator] {name} failed: {e}")
                return []

        tasks = {
            name: _guarded_scrape(name, scraper)
            for name, scraper in self.scrapers.items()
        }

        results = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )

        all_signals: List[RawSignal] = []
        for (name, _), result in zip(tasks.items(), results):
            if isinstance(result, list):
                all_signals.extend(result)
                logger.debug(f"[Aggregator] {name}: {len(result)} signals")
            elif isinstance(result, Exception):
                report_failure(name)
                logger.warning(f"[Aggregator] {name} exception: {result}")

        return all_signals

    def _deduplicate(self, signals: List[RawSignal]) -> List[RawSignal]:
        """
        Remove duplicate signals.
        Two signals are duplicates if:
          - Same URL, OR
          - Same source_id on same platform, OR
          - Near-identical title (title hash within small edit distance)
        """
        seen_urls: set = set()
        seen_ids: set = set()
        seen_title_hashes: set = set()
        unique: List[RawSignal] = []

        for signal in signals:
            # URL check
            if signal.url and signal.url in seen_urls:
                continue

            # Source ID check
            platform_id = f"{signal.platform}::{signal.source_id}"
            if platform_id in seen_ids:
                continue

            # Title hash check (first 50 chars, lowercased)
            title_key = hashlib.md5(
                signal.title[:50].lower().strip().encode()
            ).hexdigest()
            if title_key in seen_title_hashes:
                continue

            # Accept
            if signal.url:
                seen_urls.add(signal.url)
            seen_ids.add(platform_id)
            seen_title_hashes.add(title_key)
            unique.append(signal)

        return unique

    def _filter_by_age(self, signals: List[RawSignal]) -> List[RawSignal]:
        """Keep only signals published within the last MAX_SIGNAL_AGE_HOURS."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_SIGNAL_AGE_HOURS)
        fresh = []
        for signal in signals:
            if signal.published_at and signal.published_at.tzinfo is None:
                signal.published_at = signal.published_at.replace(tzinfo=timezone.utc)
            if signal.scraped_at and signal.scraped_at.tzinfo is None:
                signal.scraped_at = signal.scraped_at.replace(tzinfo=timezone.utc)
                
            published = signal.published_at or signal.scraped_at
            if published >= cutoff:
                fresh.append(signal)
        return fresh

    async def check_all_health(self) -> dict:
        """Run health checks on all scrapers. Call before first cycle."""
        results = {}
        for name, scraper in self.scrapers.items():
            try:
                ok = await scraper.health_check()
                results[name] = "OK" if ok else "FAIL"
                if ok:
                    report_success(name)
                else:
                    report_failure(name)
            except Exception as e:
                report_failure(name)
                results[name] = f"FAIL"
        return results

    def get_rate_limit_status(self) -> dict:
        """Get token bucket + circuit breaker status for all scrapers."""
        return get_all_status()
