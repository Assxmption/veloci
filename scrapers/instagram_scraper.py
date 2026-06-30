"""
scrapers/instagram_scraper.py

Instagram Reels trend scraper for VELOCI.

Fully autonomous, proxy-based scraping via Apify — no human interaction needed.
All requests run through Apify's residential proxy network, which makes the
scraping anonymous and avoids Instagram's rate limits and geo-blocking.

Three operational modes:
  1. Apify Hashtag Search (primary) — Runs apify~instagram-scraper
     actor to fetch reels by niche-specific hashtags. Rich data: likes,
     views, comments, captions, hashtags, duration.
  2. Hashtag Web Explorer (secondary) — Lightweight fallback using
     Instagram's public hashtag endpoints.
  3. Seed Corpus (fallback) — Ensures the pipeline never has zero IG signals.

NO Playwright. NO browser. NO login. NO VPN. NO manual proxy config.
Everything goes through Apify's infrastructure = fully anonymous.

Data mapping (Apify → RawSignal):
  Apify Field           →  RawSignal Field
  ─────────────────────────────────────────────────────
  caption               →  title (first line) + body (rest)
  likesCount            →  score
  videoViewCount        →  views
  videoPlayCount        →  views (fallback)
  commentsCount         →  comments
  hashtags (extracted)  →  hashtags[]
  url / shortCode       →  url
  timestamp             →  published_at
  type                  →  raw_data.content_type
  taggedUsers           →  raw_data.tagged_users / keywords boost
  ownerUsername          →  raw_data.owner
  childPosts            →  aggregated engagement (carousel support)
  audioUrl              →  raw_data.audio_url (trending audio detection)
  alt                   →  body supplement (accessibility text)

Setup:
  1. Get Apify API token: https://console.apify.com/account/integrations
  2. Add to .env: APIFY_TOKEN=apify_api_xxxxx
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set

import json as _json
import httpx
from loguru import logger

from config import PLATFORM_TRUST, NICHES
from scrapers.base import BaseScraper, RawSignal

# ─── ENV ──────────────────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# ─── APIFY ACTORS ────────────────────────────────────────────────────────────
# Verified actor IDs from Apify Store (https://apify.com/store)
# NOTE: Apify API uses ~ separator in URLs (not /)
HASHTAG_ACTOR = "apify~instagram-scraper"          # General IG scraper (supports hashtag URLs)
POST_ACTOR = "apify~instagram-reel-scraper"         # Reels-specific scraper

# API endpoints
APIFY_BASE = "https://api.apify.com/v2"

# ─── APIFY FREE TIER BUDGET ──────────────────────────────────────────────────
# Free plan: $5/month platform credits
# Instagram scraper: ~$0.05-0.10 per run (depending on results)
# Budget: max 50 actor runs/month to stay well within free tier
# That's ~1.6 runs/day, enough for 2-3 niche cycles
APIFY_MAX_RUNS_PER_MONTH = 50
APIFY_RESULTS_PER_RUN = 20       # Keep low to save credits
APIFY_MAX_HASHTAGS_PER_RUN = 6   # Max hashtags per actor run
APIFY_BUDGET_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".apify_budget.json"
)

# ─── CACHED CORPUS (hardcoded Apify data for when live API is exhausted) ─────
CORPUS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "instagram_corpus.json"
)

# ─── EXPANDED NICHE HASHTAG CORPUS ──────────────────────────────────────────
# Each niche has 15-25 targeted hashtags covering the full spectrum.
INSTAGRAM_HASHTAG_CORPUS: Dict[str, List[str]] = {
    "tech_ai": [
        "artificialintelligence", "chatgpt", "tech", "coding",
        "startup", "machinelearning", "ai", "programming",
        "openai", "gemini", "deeplearning", "techinnovation",
        "softwaredeveloper", "pythonprogramming", "aitools",
        "cloudcomputing", "saas", "automation", "robotics",
        "datascience", "neuralnetwork", "llm", "gpt",
        "techstartup", "appdevelopment",
    ],
    "finance": [
        "stockmarket", "investing", "crypto", "finance",
        "trading", "bitcoin", "personalfinance", "money",
        "nifty", "sensex", "mutualfunds", "wealthmanagement",
        "ethereum", "defi", "forextrading", "daytrading",
        "financialfreedom", "stocks", "investingtips",
        "cryptocurrency", "fintech", "budgeting",
        "stockmarketindia", "nifty50", "banknifty",
    ],
    "entertainment": [
        "viral", "comedy", "memes", "bollywood", "movies",
        "gaming", "music", "kpop", "anime", "funny",
        "dance", "challenges", "reelscomedy",
        "cinemaaddict", "moviereview", "binge", "webseries",
        "standup", "memesdaily", "funnyvideos",
        "entertainmentnews", "celebrity", "indianmemes",
        "marvelstudios", "netflixindia",
    ],
    "education": [
        "studytips", "edtech", "onlinelearning", "studymotivation",
        "learnwithme", "upsc", "competitiveexams", "iit",
        "studygram", "examprep", "learning", "knowledge",
        "skilldevelopment", "coursera", "udemy",
    ],
    "health_fitness": [
        "fitness", "gym", "workout", "yoga", "nutrition",
        "healthylifestyle", "weightloss", "bodybuilding",
        "mindfulness", "mentalhealth", "selfcare", "wellness",
        "fitfam", "fitnessmotivation", "homeworkout",
    ],
}

# Instagram-specific noise words to filter from hashtag analysis
INSTA_NOISE_TAGS = {
    "reels", "reel", "viral", "viralvideo", "trending", "trendingreels",
    "fyp", "foryou", "foryoupage", "explore", "explorepage", "follow",
    "followme", "like", "likeforlikes", "instagram", "instagood",
    "instadaily", "share", "comment", "subscribe", "new", "post",
    "content", "video", "reelsvideo", "reelsindia", "virul",
    "reelsinstagram", "repost",
}


class InstagramScraper(BaseScraper):
    """
    Instagram Reels scraper — fully autonomous via Apify proxy infrastructure.
    No browser, no login, no VPN, no manual config needed.

    Free tier budget tracking:
      - Max 50 actor runs/month ($5 free credits)
      - 20 results per run, 6 hashtags per run
      - Budget tracked in .apify_budget.json
    """

    def __init__(self):
        super().__init__(
            name="instagram_reels",
            trust_weight=PLATFORM_TRUST.get("instagram_reels", 0.73),
        )
        self._apify_available = bool(APIFY_TOKEN and len(APIFY_TOKEN) > 10)
        self._client: Optional[httpx.AsyncClient] = None
        self._budget = self._load_budget()

    # ─── BUDGET TRACKING ──────────────────────────────────────────────────────

    @staticmethod
    def _load_budget() -> dict:
        """Load monthly Apify budget from disk."""
        import json
        try:
            with open(APIFY_BUDGET_FILE, "r") as f:
                data = json.load(f)
            # Reset if month changed
            current_month = datetime.now(timezone.utc).strftime("%Y-%m")
            if data.get("month") != current_month:
                return {"month": current_month, "runs": 0, "last_run": None}
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "month": datetime.now(timezone.utc).strftime("%Y-%m"),
                "runs": 0,
                "last_run": None,
            }

    def _save_budget(self):
        """Save monthly Apify budget to disk."""
        import json
        try:
            with open(APIFY_BUDGET_FILE, "w") as f:
                json.dump(self._budget, f, indent=2, default=str)
        except Exception as e:
            logger.debug(f"[Instagram] Budget save failed: {e}")

    def _can_use_apify(self) -> bool:
        """Check if we're within our free tier budget."""
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if self._budget.get("month") != current_month:
            self._budget = {"month": current_month, "runs": 0, "last_run": None}
        runs_used = self._budget.get("runs", 0)
        if runs_used >= APIFY_MAX_RUNS_PER_MONTH:
            logger.warning(
                f"[Instagram] Apify budget exhausted: {runs_used}/{APIFY_MAX_RUNS_PER_MONTH} "
                f"runs this month. Using fallback."
            )
            return False
        remaining = APIFY_MAX_RUNS_PER_MONTH - runs_used
        logger.info(
            f"[Instagram] Apify budget: {runs_used}/{APIFY_MAX_RUNS_PER_MONTH} "
            f"runs used ({remaining} remaining)"
        )
        return True

    def _record_apify_run(self):
        """Record an Apify actor run against the monthly budget."""
        self._budget["runs"] = self._budget.get("runs", 0) + 1
        self._budget["last_run"] = datetime.now(timezone.utc).isoformat()
        self._save_budget()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=90,
                headers={
                    "User-Agent": "VELOCI/2.0 TrendEngine",
                    "Accept": "application/json",
                },
            )
        return self._client

    # ─── HEALTH CHECK ─────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Test if Instagram scraping is available."""
        if self._apify_available:
            try:
                client = await self._get_client()
                r = await client.get(
                    f"{APIFY_BASE}/acts/{HASHTAG_ACTOR}",
                    params={"token": APIFY_TOKEN},
                )
                if r.status_code == 200:
                    budget_ok = self._can_use_apify()
                    status = "proxy mode" if budget_ok else "budget exhausted, fallback"
                    logger.info(f"[Instagram] Apify API health OK ({status})")
                    return True
                else:
                    logger.warning(
                        f"[Instagram] Apify API returned {r.status_code}, "
                        f"falling back to hashtag explorer"
                    )
            except Exception as e:
                logger.warning(f"[Instagram] Apify health check failed: {e}")

        # Fallback always available via seed corpus
        logger.info("[Instagram] Seed corpus fallback always available")
        return True

    # ─── MAIN SCRAPE ────────────────────────────────────────────────────────────

    async def scrape(self, niche: str, niche_config: dict) -> List[RawSignal]:
        """
        Scrape Instagram for trend signals — fully autonomous.

        Strategy (4-tier fallback chain):
          1. Apify live hashtag scraper (proxy-based, anonymous, rich data)
          2. Cached corpus (real Apify data hardcoded from previous scrapes)
          3. Hashtag web exploration (lightweight, no credits needed)
          4. Seed signals (ensures pipeline never has zero IG data)
        """
        signals: List[RawSignal] = []

        # Mode 1: Apify live proxy scrape (autonomous, anonymous, budget-tracked)
        if self._apify_available and self._can_use_apify():
            try:
                apify_signals = await self._scrape_via_apify(niche, niche_config)
                signals.extend(apify_signals)
                logger.info(
                    f"[Instagram] Apify live: {len(apify_signals)} signals for {niche}"
                )
            except Exception as e:
                logger.warning(f"[Instagram] Apify live scrape failed: {e}")

        # Mode 2: Cached corpus — real Apify data from previous scrapes
        #         Used when Apify budget/monthly limit is exhausted.
        #         Contains real engagement data, hashtags, tagged users.
        if len(signals) < 5:
            try:
                corpus_signals = self._load_corpus_signals(niche)
                signals.extend(corpus_signals)
                if corpus_signals:
                    logger.info(
                        f"[Instagram] Cached corpus: {len(corpus_signals)} "
                        f"signals for {niche}"
                    )
            except Exception as e:
                logger.warning(f"[Instagram] Corpus load failed: {e}")

        # Mode 3: Hashtag web exploration (no credits needed)
        if len(signals) < 5:
            try:
                hashtag_signals = await self._scrape_hashtag_explore(
                    niche, niche_config
                )
                signals.extend(hashtag_signals)
                logger.info(
                    f"[Instagram] Hashtag explorer: {len(hashtag_signals)} signals"
                )
            except Exception as e:
                logger.warning(f"[Instagram] Hashtag explore failed: {e}")

        # Mode 4: Seed signals from expanded hashtag corpus
        if len(signals) < 3:
            seed_signals = self._generate_seed_signals(niche, niche_config)
            signals.extend(seed_signals)

        return signals

    # ─── CACHED CORPUS LOADER ────────────────────────────────────────────────

    def _load_corpus_signals(self, niche: str) -> List[RawSignal]:
        """
        Load real Instagram data from the cached Apify corpus file.
        
        This uses data extracted from actual Apify scrapes (hardcoded).
        When the Apify live API is rate-limited or budget-exhausted,
        this provides real engagement metrics, hashtags, tagged users,
        and captions instead of empty seed signals.
        
        Items are filtered by niche_tags to only return relevant posts.
        Each item is run through the same _apify_item_to_signal mapper
        used for live API results, ensuring identical signal quality.
        """
        if not os.path.exists(CORPUS_FILE):
            logger.debug("[Instagram] Corpus file not found, skipping")
            return []

        try:
            with open(CORPUS_FILE, "r", encoding="utf-8") as f:
                corpus = _json.load(f)
        except (OSError, _json.JSONDecodeError) as e:
            logger.warning(f"[Instagram] Corpus parse error: {e}")
            return []

        if not isinstance(corpus, list):
            return []

        # Filter items by niche_tags
        niche_items = [
            item for item in corpus
            if niche in item.get("niche_tags", [])
        ]

        if not niche_items:
            logger.debug(f"[Instagram] No corpus items for niche={niche}")
            return []

        # Run through the same mapper as live Apify data
        signals: List[RawSignal] = []
        for item in niche_items:
            signal = self._apify_item_to_signal(item, niche)
            if signal:
                # Mark as corpus-sourced in raw_data
                signal.raw_data["source_type"] = "instagram_cached_corpus"
                signals.append(signal)

        logger.info(
            f"[Instagram] Corpus: {len(niche_items)} items matched niche={niche}, "
            f"{len(signals)} valid signals"
        )
        return signals

    # ─── APIFY PROXY SCRAPE (PRIMARY) ────────────────────────────────────────

    async def _scrape_via_apify(
        self, niche: str, niche_config: dict
    ) -> List[RawSignal]:
        """
        Primary autonomous scrape via Apify hashtag search.
        
        Builds hashtag explore URLs from our expanded corpus and sends them
        to the Apify Instagram scraper which runs through residential proxies.
        No browser, no login, no credentials needed.
        """
        client = await self._get_client()
        hashtags = self._get_niche_hashtags(niche, niche_config)

        # Build hashtag explore URLs for Apify
        hashtag_urls = [
            f"https://www.instagram.com/explore/tags/{tag}/"
            for tag in hashtags[:APIFY_MAX_HASHTAGS_PER_RUN]
        ]

        payload = {
            "directUrls": hashtag_urls,
            "resultsType": "posts",
            "resultsLimit": APIFY_RESULTS_PER_RUN,
            "searchType": "hashtag",
            "searchLimit": APIFY_RESULTS_PER_RUN,
        }

        logger.info(
            f"[Instagram] Apify hashtag search: {len(hashtag_urls)} tags "
            f"({', '.join(hashtags[:APIFY_MAX_HASHTAGS_PER_RUN])})"
        )

        run_url = f"{APIFY_BASE}/acts/{HASHTAG_ACTOR}/runs"
        r = await client.post(
            run_url,
            params={"token": APIFY_TOKEN},
            json=payload,
        )

        if r.status_code not in (200, 201):
            logger.warning(
                f"[Instagram] Apify actor start failed ({r.status_code}): "
                f"{r.text[:200]}"
            )
            return []

        run_data = r.json().get("data", {})
        run_id = run_data.get("id")
        dataset_id = run_data.get("defaultDatasetId")

        if not dataset_id:
            logger.warning("[Instagram] No dataset ID returned from Apify")
            return []

        logger.info(f"[Instagram] Apify run started: {run_id}")

        # Poll for results
        items = await self._poll_apify_results(client, run_id, dataset_id)
        if not items:
            logger.info("[Instagram] Apify returned 0 items")
            return []

        self._record_apify_run()
        logger.info(f"[Instagram] Apify returned {len(items)} raw items")

        # Convert to signals
        signals: List[RawSignal] = []
        for item in items:
            signal = self._apify_item_to_signal(item, niche)
            if signal:
                signals.append(signal)

            # Also process childPosts (carousel items with their own engagement)
            child_posts = item.get("childPosts", [])
            if isinstance(child_posts, list):
                for child in child_posts[:3]:  # Max 3 children per parent
                    child_signal = self._apify_child_to_signal(child, item, niche)
                    if child_signal:
                        signals.append(child_signal)

        logger.info(
            f"[Instagram] Mapped {len(signals)} signals "
            f"(incl. carousel children)"
        )
        return signals

    async def _poll_apify_results(
        self, client: httpx.AsyncClient, run_id: str, dataset_id: str
    ) -> list:
        """Poll Apify for run completion and fetch results."""
        for attempt in range(18):  # 180s max wait
            await asyncio.sleep(10)
            try:
                status_r = await client.get(
                    f"{APIFY_BASE}/actor-runs/{run_id}",
                    params={"token": APIFY_TOKEN},
                )
                if status_r.status_code == 200:
                    status = status_r.json().get("data", {}).get("status", "")
                    if status == "SUCCEEDED":
                        logger.info(
                            f"[Instagram] Apify run succeeded after {(attempt+1)*10}s"
                        )
                        break
                    elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                        logger.warning(f"[Instagram] Apify run status: {status}")
                        return []
                    else:
                        logger.debug(
                            f"[Instagram] Apify polling ({attempt+1}/18): {status}"
                        )
            except Exception as e:
                logger.debug(f"[Instagram] Poll error: {e}")
                continue

        # Fetch results from dataset
        try:
            items_r = await client.get(
                f"{APIFY_BASE}/datasets/{dataset_id}/items",
                params={"token": APIFY_TOKEN, "format": "json", "limit": 150},
            )
            if items_r.status_code == 200:
                items = items_r.json()
                return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"[Instagram] Failed to fetch results: {e}")

        return []

    # ─── FIELD MAPPING ───────────────────────────────────────────────────────

    def _apify_item_to_signal(
        self, item: dict, niche: str
    ) -> Optional[RawSignal]:
        """
        Convert a single Apify Instagram result to RawSignal.
        
        Handles the full Apify schema including:
        - caption, likesCount, commentsCount, videoViewCount, videoPlayCount
        - taggedUsers (verified accounts = authority signal)
        - type (Image/Video), audioUrl, alt text
        - ownerUsername, shortCode, timestamp
        """
        url = item.get("url", "") or ""
        caption = item.get("caption", "") or ""
        alt_text = item.get("alt", "") or ""

        # Construct URL from shortCode if missing
        if not url:
            shortcode = item.get("shortCode", "") or item.get("id", "")
            if shortcode:
                url = f"https://www.instagram.com/p/{shortcode}/"
            else:
                return None

        if not caption and not alt_text:
            return None

        # ── Extract hashtags ─────────────────────────────────────────────────
        hashtags: List[str] = []

        # From explicit hashtags field
        raw_hashtags = item.get("hashtags", [])
        if isinstance(raw_hashtags, list):
            for tag in raw_hashtags:
                t = str(tag).strip().lower().strip("#")
                if t and t not in INSTA_NOISE_TAGS and len(t) >= 3:
                    hashtags.append(t)

        # From caption text
        caption_tags = re.findall(r"#(\w{3,})", caption)
        for tag in caption_tags:
            tag_lower = tag.lower()
            if tag_lower not in INSTA_NOISE_TAGS and tag_lower not in hashtags:
                hashtags.append(tag_lower)

        # ── Engagement metrics ───────────────────────────────────────────────
        likes = int(item.get("likesCount", 0) or item.get("likes", 0) or 0)
        comments = int(
            item.get("commentsCount", 0) or item.get("comments", 0) or 0
        )
        views = int(
            item.get("videoViewCount", 0)
            or item.get("videoPlayCount", 0)
            or item.get("viewCount", 0)
            or item.get("views", 0)
            or 0
        )

        # ── Tagged users (authority signal) ──────────────────────────────────
        tagged_users: List[dict] = []
        verified_tags: List[str] = []
        raw_tagged = item.get("taggedUsers", [])
        if isinstance(raw_tagged, list):
            for tu in raw_tagged:
                if isinstance(tu, dict):
                    username = tu.get("username", "")
                    is_verified = tu.get("is_verified", False)
                    if username:
                        tagged_users.append({
                            "username": username,
                            "full_name": tu.get("full_name", ""),
                            "verified": is_verified,
                        })
                        if is_verified:
                            verified_tags.append(username)

        # ── Content type ─────────────────────────────────────────────────────
        content_type = item.get("type", "Unknown") or "Unknown"
        audio_url = item.get("audioUrl", "") or ""
        owner_username = item.get("ownerUsername", "") or ""
        owner_id = item.get("ownerId", "") or ""

        # ── Parse timestamp ──────────────────────────────────────────────────
        published_at = None
        for ts_field in ("timestamp", "takenAtTimestamp", "date", "createdAt"):
            ts = item.get(ts_field)
            if ts:
                try:
                    if isinstance(ts, (int, float)):
                        published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                    else:
                        published_at = datetime.fromisoformat(
                            str(ts).replace("Z", "+00:00")
                        )
                    break
                except (ValueError, TypeError, OSError):
                    continue

        # ── Build title / body ───────────────────────────────────────────────
        # Use caption first line as title, rest as body.
        # Supplement with alt text if caption is empty.
        text_source = caption or alt_text
        lines = text_source.split("\n")
        title_line = lines[0][:120] if lines else url
        body_parts = []
        if len(lines) > 1:
            body_parts.append("\n".join(lines[1:])[:500])
        if alt_text and alt_text != caption:
            body_parts.append(f"[alt: {alt_text[:200]}]")
        body = " ".join(body_parts).strip()

        # ── Engagement density score ─────────────────────────────────────────
        engagement_density = likes + (comments * 5) + (views * 0.01)
        # Boost if verified users are tagged (authority signal)
        authority_boost = len(verified_tags) * 50
        engagement_density += authority_boost

        # ── Build keywords from hashtags + verified tags ─────────────────────
        keywords = list(hashtags[:10])
        for vt in verified_tags[:3]:
            if vt not in keywords:
                keywords.append(vt)

        return self._make_signal(
            source_id=url.rstrip("/").split("/")[-1] or f"ig_{hash(url) % 100000}",
            url=url,
            title=title_line,
            body=body[:500],
            hashtags=hashtags[:20],
            keywords=keywords[:12],
            score=likes,
            views=views,
            comments=comments,
            published_at=published_at,
            niche=niche,
            raw_data={
                "source_type": "instagram_apify_proxy",
                "content_type": content_type,
                "likes": likes,
                "views": views,
                "comments": comments,
                "hashtag_count": len(hashtags),
                "engagement_density": engagement_density,
                "authority_boost": authority_boost,
                "owner": owner_username,
                "owner_id": owner_id,
                "tagged_users": tagged_users[:10],
                "verified_tags": verified_tags,
                "has_audio": bool(audio_url),
                "audio_url": audio_url[:200] if audio_url else "",
            },
        )

    def _apify_child_to_signal(
        self, child: dict, parent: dict, niche: str
    ) -> Optional[RawSignal]:
        """
        Convert a childPost (carousel item) to a RawSignal.
        
        Carousel posts often have individual engagement data and tagged users.
        We inherit the parent caption but use the child's own engagement.
        """
        child_url = child.get("url", "") or ""
        if not child_url:
            shortcode = child.get("shortCode", "")
            if shortcode:
                child_url = f"https://www.instagram.com/p/{shortcode}/"
            else:
                return None

        # Inherit parent caption if child has none
        caption = child.get("caption", "") or parent.get("caption", "") or ""
        alt_text = child.get("alt", "") or ""
        if not caption and not alt_text:
            return None

        likes = int(child.get("likesCount", 0) or 0)
        comments = int(child.get("commentsCount", 0) or 0)
        views = int(
            child.get("videoViewCount", 0)
            or child.get("videoPlayCount", 0)
            or 0
        )

        # Skip low-engagement carousel items
        if likes == 0 and views == 0:
            return None

        # Extract hashtags from inherited caption
        hashtags: List[str] = []
        caption_tags = re.findall(r"#(\w{3,})", caption)
        for tag in caption_tags:
            tag_lower = tag.lower()
            if tag_lower not in INSTA_NOISE_TAGS and tag_lower not in hashtags:
                hashtags.append(tag_lower)

        # Tagged users on this specific child
        tagged_users = []
        for tu in child.get("taggedUsers", []) or []:
            if isinstance(tu, dict) and tu.get("username"):
                tagged_users.append(tu["username"])

        title_line = caption.split("\n")[0][:120] if caption else alt_text[:120]

        return self._make_signal(
            source_id=child_url.rstrip("/").split("/")[-1] or f"ig_child_{hash(child_url) % 100000}",
            url=child_url,
            title=title_line,
            body=caption[len(title_line):].strip()[:300],
            hashtags=hashtags[:15],
            keywords=hashtags[:8],
            score=likes,
            views=views,
            comments=comments,
            published_at=None,  # Children don't always have timestamps
            niche=niche,
            raw_data={
                "source_type": "instagram_apify_carousel",
                "content_type": child.get("type", "Unknown"),
                "likes": likes,
                "views": views,
                "comments": comments,
                "tagged_users": tagged_users[:5],
                "owner": parent.get("ownerUsername", ""),
            },
        )

    # ─── HASHTAG EXPLORER FALLBACK ──────────────────────────────────────────────

    async def _scrape_hashtag_explore(
        self, niche: str, niche_config: dict
    ) -> List[RawSignal]:
        """
        Fallback: Use Instagram's web endpoints to detect trending hashtags.
        Doesn't get rich metadata but detects what topics are active.
        """
        client = await self._get_client()
        signals: List[RawSignal] = []
        hashtags = self._get_niche_hashtags(niche, niche_config)

        for tag in hashtags[:6]:
            try:
                r = await client.get(
                    f"https://www.instagram.com/explore/tags/{tag}/",
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
                        ),
                        "Accept": "text/html,application/xhtml+xml",
                    },
                    follow_redirects=True,
                )

                if r.status_code != 200:
                    continue

                text = r.text
                post_count = 0
                count_match = re.search(
                    r'"edge_hashtag_to_media":\{"count":(\d+)', text
                )
                if count_match:
                    post_count = int(count_match.group(1))

                signal = self._make_signal(
                    source_id=f"ig_hashtag_{tag}",
                    url=f"https://www.instagram.com/explore/tags/{tag}/",
                    title=f"#{tag} trending on Instagram ({post_count:,} posts)",
                    body=f"Instagram hashtag #{tag} is active with {post_count:,} posts",
                    hashtags=[tag],
                    keywords=[tag],
                    score=min(post_count // 1000, 10000),
                    views=post_count,
                    niche=niche,
                    raw_data={
                        "source_type": "instagram_hashtag_explore",
                        "hashtag": tag,
                        "post_count": post_count,
                    },
                )
                signals.append(signal)
                await asyncio.sleep(2)

            except Exception as e:
                logger.debug(f"[Instagram] Hashtag {tag} failed: {e}")
                continue

        return signals

    # ─── SEED SIGNAL GENERATOR ──────────────────────────────────────────────────

    def _generate_seed_signals(
        self, niche: str, niche_config: dict
    ) -> List[RawSignal]:
        """
        Generate minimal seed signals from expanded corpus.
        Ensures Instagram always has presence in the pipeline.
        """
        signals: List[RawSignal] = []
        hashtags = self._get_niche_hashtags(niche, niche_config)

        for tag in hashtags[:5]:
            signals.append(
                self._make_signal(
                    source_id=f"ig_seed_{tag}",
                    url=f"https://www.instagram.com/explore/tags/{tag}/",
                    title=f"#{tag} — Instagram Reels trend signal",
                    body=f"Seed signal for Instagram hashtag #{tag}",
                    hashtags=[tag],
                    keywords=[tag],
                    score=0,
                    views=0,
                    niche=niche,
                    raw_data={"source_type": "instagram_seed"},
                )
            )

        return signals

    # ─── HELPERS ────────────────────────────────────────────────────────────────

    def _get_niche_hashtags(
        self, niche: str, niche_config: dict
    ) -> List[str]:
        """
        Get comprehensive Instagram hashtags for a niche.
        Combines:
          1. Expanded corpus hashtags (25+ per niche)
          2. Config seed keywords
          3. Twitter queries (often map to IG hashtags)
        """
        tags: List[str] = []

        # Expanded corpus
        corpus_tags = INSTAGRAM_HASHTAG_CORPUS.get(niche, [])
        tags.extend(corpus_tags)

        # Config seed keywords
        seed_keywords = niche_config.get("seed_keywords", [])
        for kw in seed_keywords[:15]:
            tag = kw.lower().replace(" ", "").replace("-", "")
            if len(tag) >= 3 and tag not in INSTA_NOISE_TAGS:
                tags.append(tag)

        # Twitter queries as IG hashtags
        for q in niche_config.get("twitter_queries", [])[:5]:
            tag = q.lower().replace(" ", "").replace("#", "")
            if len(tag) >= 3 and tag not in INSTA_NOISE_TAGS:
                tags.append(tag)

        # Deduplicate preserving order
        seen: Set[str] = set()
        unique: List[str] = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                unique.append(tag)

        return unique

    async def close(self):
        """Clean up HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
