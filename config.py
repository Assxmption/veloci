"""
VELOCI — Trend Intelligence Engine
config.py

All env vars loaded from .env file via python-dotenv.
Env vars take precedence over hardcoded defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

# ─── API CREDENTIALS ──────────────────────────────────────────────────────────
# Reddit  →  reddit.com/prefs/apps → create app (script type)
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.getenv("REDDIT_USER_AGENT", "summarizer/1.0 by u/One-Location-2228")

# YouTube  →  console.cloud.google.com → enable YouTube Data API v3 → create key
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# Twitter/X  →  developer.twitter.com → create app → bearer token (free tier)
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# NewsAPI  →  newsapi.org → free tier (100 req/day)
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# Instagram/Apify → console.apify.com → Account → Integrations → API token
# Free tier = ~$5/mo credits = ~5000 reels/mo
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# Organic Instagram Scraper required fields
IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent / "veloci.db"))

# ─── LOG SANITIZATION ─────────────────────────────────────────────────────────
# Strip API keys from ALL log output — production security requirement.
import re as _re
from loguru import logger as _logger

_SENSITIVE_VALUES = [
    v for v in [YOUTUBE_API_KEY, TWITTER_BEARER_TOKEN, NEWS_API_KEY,
                REDDIT_CLIENT_SECRET, REDDIT_CLIENT_ID, APIFY_TOKEN,
                IG_USERNAME, IG_PASSWORD]
    if v and len(v) > 4
]

def _sanitize_log(message: str) -> str:
    """Replace API keys with [REDACTED] in log messages."""
    for secret in _SENSITIVE_VALUES:
        message = message.replace(secret, "[REDACTED]")
    return message

class _SanitizeFilter:
    def __call__(self, record):
        record["message"] = _sanitize_log(record["message"])
        return True

# Apply sanitizer globally — no key ever leaks to stdout/file
_logger.configure(patcher=lambda record: record.update(
    message=_sanitize_log(record["message"])
))
# ─── NICHE CONFIG ─────────────────────────────────────────────────────────────
# 3 niches × 4 channels each = 12 channels
# Channel roles: broad, deep-dive, reaction, data
NICHES: dict = {
    "tech_ai": {
        "display_name": "Tech & AI",
        "channel_count": 4,
        "channel_angles": ["broad", "deep_dive", "reaction", "data"],
        "subreddits": [
            "technology", "artificial", "MachineLearning", "singularity",
            "futurology", "OpenAI", "ChatGPT", "LocalLLaMA", "programming",
            "startups", "hardware", "gadgets", "cybersecurity",
        ],
        "subreddits_rising": [  # Prioritise RISING (not hot) for early signal
            "technology", "artificial", "singularity", "futurology", "startups",
        ],
        "youtube_categories": ["28"],            # Science & Technology
        "youtube_region_codes": ["US", "IN", "GB"],
        "youtube_search_terms": [
            "AI news 2025", "ChatGPT update", "tech startup", "machine learning",
        ],
        "twitter_queries": [
            "AI", "ChatGPT", "OpenAI", "tech startup", "LLM", "Anthropic",
        ],
        "seed_keywords": [
            "AI", "tech", "GPT", "automation", "robot", "startup", "ML",
            "LLM", "neural", "algorithm", "data", "cloud", "chip", "quantum",
        ],
        "rss_feeds": [
            "https://feeds.feedburner.com/TechCrunch",
            "https://www.wired.com/feed/rss",
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.theverge.com/rss/index.xml",
            "https://venturebeat.com/feed/",
            "https://technode.com/feed/",
        ],
        "posting_windows_utc": ["07:00", "12:00", "18:00", "21:00"],
    },

    "finance": {
        "display_name": "Finance & Markets",
        "channel_count": 4,
        "channel_angles": ["broad", "deep_dive", "reaction", "data"],
        "subreddits": [
            "investing", "wallstreetbets", "stocks", "CryptoCurrency",
            "personalfinance", "economy", "financialindependence",
            "options", "SecurityAnalysis", "dividends", "Economics",
        ],
        "subreddits_rising": [
            "wallstreetbets", "CryptoCurrency", "stocks", "investing",
        ],
        "youtube_categories": ["25"],
        "youtube_region_codes": ["US", "GB", "IN"],
        "youtube_search_terms": [
            "stock market today", "crypto news", "investing 2025", "market crash",
        ],
        "twitter_queries": [
            "stock market", "crypto", "inflation", "Fed rate", "earnings",
            "bull run", "recession", "IPO",
        ],
        "seed_keywords": [
            "stock", "market", "crypto", "economy", "invest", "bull", "bear",
            "interest rate", "Fed", "inflation", "earnings", "IPO", "ETF",
        ],
        "rss_feeds": [
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
            "https://feeds.reuters.com/reuters/businessNews",
            "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
            "https://www.marketwatch.com/rss/topstories",
        ],
        "posting_windows_utc": ["06:00", "09:30", "16:00", "20:00"],
    },

    "entertainment": {
        "display_name": "Entertainment & Viral",
        "channel_count": 5,
        "channel_angles": ["broad", "deep_dive", "reaction", "data", "shorts"],
        "subreddits": [
            # Mainstream entertainment
            "movies", "television", "Music", "gaming", "sports",
            "popculturechat", "boxoffice", "NetflixBestOf", "esports",
            "HipHopHeads", "popheads", "MovieDetails",
            # Viral / Memes / Internet culture (KEY for reels/shorts)
            "memes", "dankmemes", "funny", "Unexpected", "nextfuckinglevel",
            "MadeMeSmile", "Satisfying", "oddlysatisfying", "facepalm",
            "therewasanattempt", "interestingasfuck", "BeAmazed",
            "PublicFreakout", "holdmybeer", "WatchPeopleDieInside",
            # Bollywood / India entertainment
            "BollyBlindsNGossip", "bollywood", "IndianGaming",
            "IndiaSpeaks", "india", "CricketShitpost",
            # K-pop & anime (massive shorts audience)
            "kpop", "anime", "manga",
            # Influencer / creator economy
            "youtube", "TikTokCringe", "Instagramreality",
        ],
        "subreddits_rising": [
            "memes", "funny", "nextfuckinglevel", "Unexpected",
            "MadeMeSmile", "interestingasfuck", "movies", "gaming",
            "BollyBlindsNGossip", "TikTokCringe",
        ],
        "youtube_categories": [
            "24",   # Entertainment
            "23",   # Comedy
            "20",   # Gaming
            "10",   # Music
            "17",   # Sports
            "1",    # Film & Animation
            "22",   # People & Blogs (where most viral content lives)
        ],
        "youtube_region_codes": ["US", "IN", "GB", "AU", "BR", "KR", "JP"],
        "youtube_search_terms": [
            "viral video 2025", "funny moments", "movie review 2025",
            "new music video", "gaming highlights", "sports highlights",
            "meme compilation", "satisfying video", "Bollywood trailer",
            "K-pop comeback", "anime moments", "prank video",
            "challenge accepted", "life hack", "street food",
        ],
        "twitter_queries": [
            "viral video", "new movie", "music release", "gaming",
            "sports score", "celebrity", "trailer", "Netflix", "review",
            "meme", "Bollywood", "K-pop", "anime", "trending sound",
            "challenge", "funny",
        ],
        "seed_keywords": [
            "movie", "TV", "music", "game", "sports", "celebrity", "trailer",
            "review", "sequel", "album", "championship", "viral",
            "meme", "funny", "prank", "challenge", "satisfying", "compilation",
            "reaction", "Bollywood", "K-pop", "anime", "influencer",
            "shorts", "reels", "hack", "unboxing", "transformation",
            "before after", "street food", "ASMR", "dance",
        ],
        "rss_feeds": [
            "https://deadline.com/feed/",
            "https://variety.com/feed/",
            "https://kotaku.com/rss",
            "https://www.ign.com/articles.rss",
            "https://comicbook.com/feed/",
            "https://www.bollywoodhungama.com/rss/news.xml",
        ],
        "posting_windows_utc": ["10:00", "14:00", "18:00", "21:00", "23:00"],
    },
}

# ─── PIPELINE SETTINGS ────────────────────────────────────────────────────────
SCRAPE_INTERVAL_MINUTES   = 30    # Full scrape cycle frequency
TREND_HISTORY_HOURS       = 48    # Window for velocity calculation
MIN_COMPOSITE_SCORE       = 0.35  # Threshold to be considered a valid trend
MAX_TRENDS_PER_NICHE      = 15    # Top N trends output per niche per cycle
NOVELTY_LOOKBACK_DAYS     = 7     # Don't resurface trends from last N days
CONTENT_VARIATION_SEED    = True  # Randomise script angle per channel

# Composite score weights (must sum to 1.0)
WEIGHTS = {
    "velocity":            0.35,  # Rate of growth in mentions
    "cross_platform":      0.25,  # Confirmed across multiple platforms
    "novelty":             0.20,  # Distance from recently published content
    "sentiment":           0.10,  # Positive sentiment = higher shareability
    "engagement_potential": 0.10, # Historical engagement for similar topics
}

# Per-platform trust weights for cross-platform scoring
PLATFORM_TRUST = {
    "google_trends_rising":  1.00,  # Best early signal, verified intent
    "reddit_rising":         0.92,  # Rising posts = 6-24h ahead of mainstream
    "twitter_velocity":      0.87,  # Real-time but noisy
    "news_rss":              0.83,  # Breaking news = early social signal
    "news_api":              0.78,
    "youtube_trending":      0.75,  # Slight lag but high-engagement validation
    "instagram_reels":       0.73,  # Engagement validation — confirms virality
    "reddit_hot":            0.65,  # Already established, lower novelty
    "gdelt":                 0.68,  # Global events, useful for context
}

# Tier classification by composite score
TREND_TIERS = {
    "early":    (0.70, 1.00),  # Catch it NOW — 12-48h before mainstream
    "emerging": (0.50, 0.70),  # Good window — act within 24h
    "trending": (0.35, 0.50),  # Still viable but saturating
    "saturated": (0.00, 0.35), # Discard
}

# ─── NLP SETTINGS ─────────────────────────────────────────────────────────────
EMBEDDING_MODEL      = "all-MiniLM-L6-v2"  # Lightweight, 384-dim, fast
CLUSTERING_EPS       = 0.28   # DBSCAN cosine distance — lower = tighter clusters
CLUSTERING_MIN_SAMPLES = 2
MIN_CROSS_SOURCE_MENTIONS = 3  # Ignore topics with fewer cross-source hits
MAX_KEYWORDS_PER_TREND = 10

# ─── GLOBAL RSS (scraped every cycle regardless of niche) ─────────────────────
GLOBAL_RSS_FEEDS = [
    # International (working from India)
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://rss.cnn.com/rss/edition.rss",
    "https://feeds.washingtonpost.com/rss/world",
    # Indian news (accessible from India)
    "https://www.ndtv.com/rss/top-stories",
    "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://www.livemint.com/rss/news",
    "https://indianexpress.com/section/india/feed/",
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
]

# ─── GOOGLE TRENDS ────────────────────────────────────────────────────────────
GOOGLE_TRENDS_GEO      = ""          # "" = worldwide
GOOGLE_TRENDS_TIMEFRAME = "now 1-d"  # Last 24h for maximum recency
GOOGLE_TRENDS_CATEGORIES = [0, 5, 7, 8, 16, 17]
# 0=All, 5=Autos, 7=Finance, 8=Food, 16=News, 17=Sports

# ─── YOUTUBE ──────────────────────────────────────────────────────────────────
YOUTUBE_MAX_RESULTS       = 50     # Per region per category
YOUTUBE_TRENDING_REGIONS  = ["US", "IN", "GB", "CA", "AU"]

# ─── TWITTER/X ────────────────────────────────────────────────────────────────
TWITTER_MAX_RESULTS     = 100      # Per query
TWITTER_LOOKBACK_HOURS  = 6        # Recent tweets only

# ─── DATABASE ────────────────────────────────────────────────────────────────
# DATABASE_PATH defined above (loads from .env with fallback to veloci.db)

# ─── LOGGING ─────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE  = "veloci_scraper.log"
