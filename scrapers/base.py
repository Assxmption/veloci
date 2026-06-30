"""
scrapers/base.py

Abstract base class for all VELOCI scrapers.
All scrapers output a list of RawSignal objects — a normalised schema
that the aggregator and NLP pipeline can work with regardless of source.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from loguru import logger


@dataclass
class RawSignal:
    """
    A single raw signal from any platform.
    Every scraper normalises its output to this schema.
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    platform: str          # e.g. "reddit_rising", "youtube_trending", "twitter"
    source_id: str         # Platform-specific ID (post_id, video_id, tweet_id)
    url: str               # Direct link to the source

    # ── Content ───────────────────────────────────────────────────────────────
    title: str             # Primary text (post title, video title, tweet text)
    body: str = ""         # Secondary text (selftext, description, article body)
    hashtags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)  # Extracted pre-NLP

    # ── Engagement ────────────────────────────────────────────────────────────
    score: int = 0         # Upvotes, likes, view_count, retweet_count
    comments: int = 0
    shares: int = 0
    views: int = 0

    # ── Time ──────────────────────────────────────────────────────────────────
    published_at: Optional[datetime] = None
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Metadata ──────────────────────────────────────────────────────────────
    niche: Optional[str] = None       # Niche this was collected for
    platform_trust: float = 0.75      # Trust weight from config.PLATFORM_TRUST
    raw_data: dict = field(default_factory=dict)  # Original API response

    @property
    def full_text(self) -> str:
        """Combined title + body for NLP processing."""
        return f"{self.title} {self.body}".strip()

    @property
    def engagement_score(self) -> float:
        """
        Normalised engagement proxy.
        We can't compare Reddit upvotes directly to YouTube views —
        this gives a log-scaled composite usable for relative ranking.
        """
        import math
        raw = self.score + (self.comments * 3) + self.shares + (self.views * 0.001)
        return math.log1p(raw)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "source_id": self.source_id,
            "url": self.url,
            "title": self.title,
            "body": self.body[:500],  # truncate for storage
            "hashtags": self.hashtags,
            "keywords": self.keywords,
            "score": self.score,
            "comments": self.comments,
            "shares": self.shares,
            "views": self.views,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "scraped_at": self.scraped_at.isoformat(),
            "niche": self.niche,
            "platform_trust": self.platform_trust,
        }


class BaseScraper(ABC):
    """
    Abstract base for all platform scrapers.

    Subclass, implement scrape() and health_check(), done.
    The orchestrator calls scrape(niche, config) and gets back List[RawSignal].
    """

    def __init__(self, name: str, trust_weight: float = 0.75):
        self.name = name
        self.trust_weight = trust_weight
        self._is_healthy: Optional[bool] = None

    @abstractmethod
    async def scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """
        Scrape signals for a given niche.

        Args:
            niche: niche key from config (e.g. "tech_ai")
            niche_config: the niche config dict from config.NICHES

        Returns:
            List of RawSignal objects, newest first.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the scraper can reach its data source."""
        ...

    async def safe_scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """
        Wrapper around scrape() with error handling and rate-limit backoff.
        Always returns a list — never raises to the orchestrator.
        """
        try:
            signals = await self.scrape(niche, niche_config)
            logger.info(f"[{self.name}] Got {len(signals)} signals for niche={niche}")
            return signals
        except Exception as e:
            logger.error(f"[{self.name}] scrape() failed for niche={niche}: {e}")
            return []

    def _make_signal(self, **kwargs) -> RawSignal:
        """Convenience factory that injects platform name and trust weight."""
        return RawSignal(
            platform=kwargs.pop("platform", self.name),
            platform_trust=kwargs.pop("platform_trust", self.trust_weight),
            **kwargs,
        )
