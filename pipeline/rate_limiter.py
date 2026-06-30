"""
pipeline/rate_limiter.py

Production-grade rate limiter for VELOCI scrapers.
Enforces FREE TIER limits for all APIs:

┌─────────────────────────────────────────────────────────────────────┐
│  Platform        │  Free Tier Limit              │  Our Budget     │
│──────────────────┼───────────────────────────────┼─────────────────│
│  YouTube API v3  │  10,000 units/day             │  8,000 units    │
│  Twitter/X v2    │  500K tweets/month (Free)     │  400K tweets    │
│  NewsAPI         │  100 requests/day             │  80 req/day     │
│  Google Trends   │  ~30 requests/hour (informal) │  20 req/hour    │
│  Reddit API      │  60 requests/minute           │  50 req/min     │
│  GDELT           │  No official limit            │  120 req/hour   │
│  Instagram/Apify │  $5/mo free credits           │  20 req/hour    │
│  RSS             │  No limit                     │  No limit       │
└─────────────────────────────────────────────────────────────────────┘

Uses token bucket algorithm with per-platform isolation.
Circuit breaker trips after 3 consecutive failures → 5-min cooldown.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
from loguru import logger


class ScraperStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"      # Rate-limited or partial failures
    CIRCUIT_OPEN = "open"      # Tripped — waiting for cooldown
    DISABLED = "disabled"      # Manually disabled or permanently unavailable


@dataclass
class TokenBucket:
    """
    Token bucket rate limiter.
    Tokens refill at a constant rate. Each request consumes tokens.
    If bucket is empty, caller must wait.
    """
    max_tokens: float
    refill_rate: float          # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = self.max_tokens
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    async def acquire(self, cost: float = 1.0) -> float:
        """
        Acquire tokens. Returns the wait time if bucket was empty.
        Will async-sleep if needed — never throws.
        """
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return 0.0

        wait_time = (cost - self.tokens) / self.refill_rate
        logger.debug(f"Rate limit: waiting {wait_time:.1f}s for {cost} tokens")
        await asyncio.sleep(wait_time)
        self._refill()
        self.tokens -= cost
        return wait_time

    @property
    def available(self) -> float:
        self._refill()
        return self.tokens


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern.
    - CLOSED (healthy): requests pass through
    - OPEN (tripped): requests blocked for cooldown_seconds
    - HALF_OPEN: one probe request allowed to test recovery
    """
    failure_threshold: int = 3
    cooldown_seconds: float = 300.0      # 5 minutes
    _failures: int = 0
    _last_failure: float = 0.0
    _state: str = "closed"

    @property
    def is_open(self) -> bool:
        if self._state == "closed":
            return False
        if self._state == "open":
            elapsed = time.monotonic() - self._last_failure
            if elapsed >= self.cooldown_seconds:
                self._state = "half_open"
                logger.info("Circuit breaker → HALF_OPEN (probe allowed)")
                return False
            return True
        return False  # half_open allows one probe

    def record_success(self):
        self._failures = 0
        if self._state != "closed":
            logger.info("Circuit breaker → CLOSED (recovered)")
        self._state = "closed"

    def record_failure(self):
        self._failures += 1
        self._last_failure = time.monotonic()
        if self._failures >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                f"Circuit breaker → OPEN "
                f"({self._failures} failures, cooldown {self.cooldown_seconds}s)"
            )

    @property
    def state(self) -> str:
        # Re-check for timeout transitions
        _ = self.is_open
        return self._state


# ─── FREE TIER BUDGETS ────────────────────────────────────────────────────────

# YouTube: 10K units/day. Most search/list calls = 100 units.
# At 30-min cycles × 3 niches × ~3 calls = 9 calls/cycle = 900 units/cycle
# 48 cycles/day × 900 = 43,200 → TOO MUCH. Cap at ~80 calls/day = 8000 units
YOUTUBE_BUCKET = TokenBucket(
    max_tokens=8.0,             # 8 calls available at burst
    refill_rate=8.0 / 86400,    # 80 calls / day → ~0.00093 calls/sec
)

# Twitter: 500K tweets/month free → ~16,667/day → ~694/hour
# We search ~100 results per query, 2 queries per niche per cycle
# 3 niches × 2 queries × 48 cycles = 288 searches/day — well within budget
TWITTER_BUCKET = TokenBucket(
    max_tokens=5.0,
    refill_rate=5.0 / 3600,     # 5 calls/hour
)

# NewsAPI: 100 requests/day free tier
# 3 niches × 1 query × 48 cycles = 144 → cap at ~80/day
NEWSAPI_BUCKET = TokenBucket(
    max_tokens=3.0,
    refill_rate=80.0 / 86400,   # 80 calls/day
)

# Google Trends: informal ~30 requests/hour before 429
# Use conservative 20/hour
GTRENDS_BUCKET = TokenBucket(
    max_tokens=3.0,
    refill_rate=20.0 / 3600,    # 20 calls/hour
)

# Reddit: 60 requests/minute (OAuth)
# Very generous — we use maybe 3-5 per cycle
REDDIT_BUCKET = TokenBucket(
    max_tokens=10.0,
    refill_rate=50.0 / 60,      # 50 calls/minute
)

# GDELT: no official limit but be respectful
GDELT_BUCKET = TokenBucket(
    max_tokens=5.0,
    refill_rate=120.0 / 3600,   # 120 calls/hour
)

# Instagram: Apify API — ~$5/mo free credits, ~20 calls/hour safe
INSTAGRAM_BUCKET = TokenBucket(
    max_tokens=4.0,
    refill_rate=20.0 / 3600,    # 20 calls/hour
)


# ─── CIRCUIT BREAKERS (per scraper) ──────────────────────────────────────────

CIRCUIT_BREAKERS: Dict[str, CircuitBreaker] = {
    "reddit": CircuitBreaker(failure_threshold=3, cooldown_seconds=300),
    "youtube": CircuitBreaker(failure_threshold=3, cooldown_seconds=300),
    "google_trends": CircuitBreaker(failure_threshold=3, cooldown_seconds=600),
    "twitter": CircuitBreaker(failure_threshold=3, cooldown_seconds=600),
    "news": CircuitBreaker(failure_threshold=3, cooldown_seconds=300),
    "instagram": CircuitBreaker(failure_threshold=3, cooldown_seconds=600),
    "gdelt": CircuitBreaker(failure_threshold=3, cooldown_seconds=300),
}


# ─── RATE LIMITER MAP ────────────────────────────────────────────────────────

RATE_LIMITERS: Dict[str, TokenBucket] = {
    "reddit": REDDIT_BUCKET,
    "youtube": YOUTUBE_BUCKET,
    "google_trends": GTRENDS_BUCKET,
    "twitter": TWITTER_BUCKET,
    "news": NEWSAPI_BUCKET,
    "instagram": INSTAGRAM_BUCKET,
    "gdelt": GDELT_BUCKET,
}


async def check_rate_limit(scraper_name: str, cost: float = 1.0) -> bool:
    """
    Check rate limit AND circuit breaker before making a call.
    Returns True if the call is allowed, False if blocked.
    """
    # Check circuit breaker first
    cb = CIRCUIT_BREAKERS.get(scraper_name)
    if cb and cb.is_open:
        logger.warning(f"[{scraper_name}] Circuit breaker OPEN — skipping")
        return False

    # Check rate limit
    bucket = RATE_LIMITERS.get(scraper_name)
    if bucket:
        await bucket.acquire(cost)

    return True


def report_success(scraper_name: str):
    """Call after a successful scrape to reset circuit breaker."""
    cb = CIRCUIT_BREAKERS.get(scraper_name)
    if cb:
        cb.record_success()


def report_failure(scraper_name: str):
    """Call after a failed scrape to increment circuit breaker."""
    cb = CIRCUIT_BREAKERS.get(scraper_name)
    if cb:
        cb.record_failure()


def get_all_status() -> Dict[str, dict]:
    """Get status of all rate limiters and circuit breakers."""
    status = {}
    for name in RATE_LIMITERS:
        bucket = RATE_LIMITERS[name]
        cb = CIRCUIT_BREAKERS.get(name)
        status[name] = {
            "tokens_available": round(bucket.available, 2),
            "max_tokens": bucket.max_tokens,
            "circuit_state": cb.state if cb else "none",
            "failures": cb._failures if cb else 0,
        }
    return status
