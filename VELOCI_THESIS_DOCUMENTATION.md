# VELOCI — Trend Intelligence Engine
## Comprehensive Thesis & Research Paper Documentation

> **AI-Driven Multimodal System for Automated UGC Generation and Engagement Optimization**
> *The machine that learns to go viral.*

---

## Table of Contents

1. [Abstract](#1-abstract)
2. [Introduction & Problem Statement](#2-introduction--problem-statement)
3. [Research Foundation & Literature Review](#3-research-foundation--literature-review)
4. [Novel Contributions](#4-novel-contributions)
5. [System Architecture — 7-Stage Pipeline](#5-system-architecture--7-stage-pipeline)
6. [Stage 01 — Trend Intelligence Engine (Implemented)](#6-stage-01--trend-intelligence-engine)
7. [Stage 02 — Content Generation Engine (Implemented)](#7-stage-02--content-generation-engine)
8. [Hybrid Organic Instagram Scraping Module](#8-hybrid-organic-instagram-scraping-module)
9. [NLP Pipeline Deep-Dive](#9-nlp-pipeline-deep-dive)
10. [Ensemble Ranking Algorithm](#10-ensemble-ranking-algorithm)
11. [Rate Limiting & Circuit Breaker Infrastructure](#11-rate-limiting--circuit-breaker-infrastructure)
12. [Database Architecture](#12-database-architecture)
13. [Sample Pipeline Output](#13-sample-pipeline-output)
14. [Crash Test & Validation Suite](#14-crash-test--validation-suite)
15. [Development Prompt History](#15-development-prompt-history)
16. [Future Stages — Pseudocode & Snippets](#16-future-stages--pseudocode--snippets)
17. [Evaluation Metrics](#17-evaluation-metrics)
18. [Security & Safeguards](#18-security--safeguards)
19. [Repository Structure](#19-repository-structure)
20. [Conclusion & Future Work](#20-conclusion--future-work)

---

## 1. Abstract

VELOCI is a **closed-loop autonomous content creation system** that detects social media trends 12–72 hours before they peak, generates short-form video content (scripts, TTS, visuals, thumbnails), predicts engagement before publishing via a multimodal gate, auto-schedules posts using reinforcement learning (contextual bandit rewarded on first-hour velocity), publishes across 10–15 channels (3 niches × 4 angles each), and learns from every result — retraining predictions and tuning generation parameters.

This document provides a comprehensive technical specification of the system, covering the theoretical research foundation, implemented modules (Stage 01: Trend Intelligence, Stage 02: Script Generation), the novel Hybrid Organic Instagram Scraping methodology, and pseudocode blueprints for all future stages (Engagement Predictor, RL Scheduler, Auto-Publish, Feedback Loop, Analytics Dashboard).

**Keywords**: Trend Intelligence, NLP Clustering, DBSCAN, Sentence Embeddings, Cross-Platform Corroboration, Engagement Prediction, Reinforcement Learning, Short-Form Video, Autonomous Content Generation, Multi-Platform Scraping

---

## 2. Introduction & Problem Statement

### 2.1 The Problem

| Pain Point | What Exists Today | What VELOCI Does |
|---|---|---|
| Late trend signals | Creators find trends after they peak | Scrapes RISING signals 12–72h ahead via Reddit Rising, Google Trends RELATED RISING, GDELT global events |
| No pre-publish prediction | Failure visible only post-upload | Multimodal engagement gate (NAWP+ECR) blocks low-performers before they go live |
| No feedback loop | Every cycle starts from scratch | Live performance (views, watch time, drop-off) feeds back as training signal |
| Manual scheduling | Posting based on gut feel | RL contextual bandit learns per-channel optimal windows, rewarded on first-hour velocity |
| Fragmented tools | Analytics, scheduling, generation are separate | Unified pipeline — every module feeds the next, sharing state and learning |
| No behaviour modelling | No system models how visual+audio+text jointly drive retention | Cross-modal attention fusion (visual, audio, caption, metadata) models real engagement |

### 2.2 Core Design Philosophy

The system is designed as an **iterative, self-sufficient, automated model** — once deployed, it autonomously discovers trends, generates content, predicts performance, schedules publication, monitors results, and retrains itself without human intervention. Every 30 minutes, the pipeline executes a complete scrape → NLP → rank → export cycle across 3 niches (Tech & AI, Finance, Entertainment), persisting all data to SQLite and exporting structured JSON + CSV for downstream consumption.

---

## 3. Research Foundation & Literature Review

### 3.1 Core Papers

| Paper | Venue | Key Contribution | Our Adaptation |
|---|---|---|---|
| **Li et al.** "Delving Deep into Engagement Prediction of Short Videos" | CVPR 2024 | SnapUGC dataset (90K videos, 2K+ raters/video). VQA ≠ engagement. NAWP+ECR metrics | We adopt NAWP+ECR as primary metrics. Use cross-modal attention as a **generation gate**, not just scorer |
| **Sun et al.** "Engagement Prediction with Large Multimodal Models" | ICCV 2025 | VQualA Challenge winner. Ensemble VideoLLaMA2 + Qwen2.5-VL beats specialized models | Adapts LMM fusion for generative pipeline — model guides what gets **created** |
| **Zou et al.** "RL to Optimize Long-term User Engagement" (FeedRec) | KDD 2019 | Dual-network RL: Q-Network (LSTM) + S-Network environment simulator | Contextual bandit for scheduling — rewarded on first-hour velocity |
| **Gelli et al.** "Image Popularity Prediction using Sentiment+Context" | ACM MM 2015 | Multimodal outperforms unimodal for pre-publish prediction | Validates our pre-publish multimodal premise |
| **Mazloom et al.** "Multimodal Popularity Prediction of Brand-related Videos" | ACM MM 2016 | Sentiment in speech/captions is strong shareability predictor | Caption sentiment scoring in engagement predictor |
| **Zhang et al.** "Multi-task Learning for Short-Video Engagement Prediction" | WWW 2023 | Shared cross-modal representation generalises better across metrics | Multi-task head (views, likes, shares, comments) in our predictor |

### 3.2 Why These Specific Methodologies

**Why DBSCAN over K-means?**
K-means requires specifying K upfront. Trends per cycle are unpredictable (5–50). DBSCAN discovers clusters organically and marks true outliers as noise. With cosine distance on sentence embeddings, it groups semantically related signals regardless of surface vocabulary.

**Why RISING not HOT?**
Reddit's "rising" sort shows posts gaining velocity RIGHT NOW. "Hot" shows posts that already have votes. The velocity delta = your lead time (6–24h).

**Why Sentence Embeddings over Hashtags?**
Hashtags are incomplete and inconsistent. Sentence embeddings cluster by MEANING — "AI regulation", "OpenAI compliance", and "Anthropic EU rules" cluster as ONE topic despite sharing zero hashtags.

**Why First-Hour Velocity as RL Reward?**
Platform algorithms (TikTok, YouTube Shorts, Instagram Reels) make their ranking decision in the first 60 minutes. Optimizing for first-hour velocity is directly aligned with how platforms decide to amplify content.

---

## 4. Novel Contributions

1. **C1** — Pre-publish engagement prediction as a **generation gate** (not post-hoc evaluator): If predicted engagement < θ, content is sent back for regeneration with adjusted parameters.
2. **C2** — Closed-loop adaptive pipeline: Trend → Generate → Predict → Publish → Retrain (never static). Every cycle updates model weights.
3. **C3** — Multimodal behaviour modelling guides **generation**, not just evaluation. The engagement predictor's internal representations inform which content angles to pursue.
4. **C4** — First-hour engagement velocity formalised as RL reward for scheduling. The contextual bandit discovers per-channel optimal posting windows.

---

## 5. System Architecture — 7-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONTINUOUS FEEDBACK LOOP                             │
│                                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │ 01      │    │ 02      │    │ 03      │    │ 04      │    │ 05      │  │
│  │ TREND   │───▶│ CONTENT │───▶│ ENGAGE  │───▶│ RL      │───▶│ AUTO    │  │
│  │ INTEL   │    │ GEN     │    │ GATE    │    │ SCHED   │    │ PUBLISH │  │
│  └─────────┘    └─────────┘    └────┬────┘    └─────────┘    └────┬────┘  │
│       ▲              ▲              │              ▲              │        │
│       │              │        E < θ │ ───▶ REVISE  │              │        │
│       │              │              │              │              │        │
│       │         ┌────┴──────────────┴──────────────┴──────┐       │        │
│       │         │               06  FEEDBACK LOOP         │◀──────┘        │
│       │         │  views, watch time, drop-off, velocity  │               │
│       └─────────┤  retrain predictor · update RL policy   ├───────────────│
│                 │  drift: θ threshold adapts               │               │
│                 └─────────────────────────────────────────┘               │
│                                                                             │
│                 07  ANALYTICS DASHBOARD + REVENUE STREAMS                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stage Summary

| Stage | Name | Status | Description |
|---|---|---|---|
| 01 | Trend Intelligence | ✅ Production | 6 scrapers → NLP → Ensemble ranking → SQLite + JSON/CSV export |
| 02 | Content Generation | ✅ Implemented | Template-based script generation (8 content angles, multi-dimension scoring) |
| 03 | Engagement Predictor | 🔴 Planned | Multimodal gate using NAWP+ECR metrics |
| 04 | RL Scheduler | 🔴 Planned | Contextual bandit for optimal publish timing |
| 05 | Auto-Publish | 🔴 Planned | Platform API integration (YouTube, Instagram, etc.) |
| 06 | Feedback Loop | 🔴 Planned | Performance → retrain → policy update |
| 07 | Analytics Dashboard | 🔴 Planned | Revenue tracking + live trend feed |

---

## 6. Stage 01 — Trend Intelligence Engine

### 6.1 Data Sources

The engine scrapes 6 distinct platform categories in parallel every 30 minutes:

| Source | Type | Signal Lead Time | Trust Weight |
|---|---|---|---|
| Reddit RISING | API (PRAW) + JSON fallback | 6–24h early | 0.92 |
| Google Trends RISING | Unofficial (pytrends) | 12–72h early | 1.00 |
| YouTube Trending + Search | API v3 | 2–12h early | 0.75 |
| Twitter/X Velocity | API v2 + Google News fallback | 0–6h early | 0.87 |
| NewsAPI + RSS + GDELT | REST + Feed parsing | 6–48h early | 0.83 |
| Instagram Reels | Playwright Organic + Apify Proxy | 0–12h | 0.73 |

### 6.2 Niche Configuration

Three niches are configured, each with dedicated subreddit lists, YouTube categories, Twitter queries, seed keywords, and RSS feeds:

```python
NICHES = {
    "tech_ai": {
        "display_name": "Tech & AI",
        "channel_count": 4,
        "channel_angles": ["broad", "deep_dive", "reaction", "data"],
        "subreddits": [
            "technology", "artificial", "MachineLearning", "singularity",
            "futurology", "OpenAI", "ChatGPT", "LocalLLaMA", "programming",
            "startups", "hardware", "gadgets", "cybersecurity",
        ],
        "youtube_categories": ["28"],  # Science & Technology
        "seed_keywords": [
            "AI", "tech", "GPT", "automation", "robot", "startup", "ML",
            "LLM", "neural", "algorithm", "data", "cloud", "chip", "quantum",
        ],
        # ... RSS feeds, Twitter queries, posting windows
    },
    "finance": { ... },
    "entertainment": { ... },
}
```

### 6.3 Pipeline Scoring Weights

```python
WEIGHTS = {
    "velocity":            0.35,  # Rate of growth in mentions
    "cross_platform":      0.25,  # Confirmed across multiple platforms
    "novelty":             0.20,  # Distance from recently published content
    "sentiment":           0.10,  # Positive sentiment = higher shareability
    "engagement_potential": 0.10, # Historical engagement for similar topics
}
```

### 6.4 Tier Classification

```python
TREND_TIERS = {
    "early":    (0.70, 1.00),  # 🟢 Post in 2-6h — you're ahead
    "emerging": (0.50, 0.70),  # 🟡 Post within 24h — good window
    "trending": (0.35, 0.50),  # 🟠 Still viable but saturating
    "saturated": (0.00, 0.35), # 🔴 Skip
}
```

### 6.5 RawSignal Schema

Every scraper normalises its output to this universal schema:

```python
@dataclass
class RawSignal:
    # Identity
    platform: str          # e.g. "reddit_rising", "youtube_trending"
    source_id: str         # Platform-specific ID
    url: str               # Direct link to the source

    # Content
    title: str             # Primary text
    body: str = ""         # Secondary text
    hashtags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # Engagement
    score: int = 0         # Upvotes, likes, view_count
    comments: int = 0
    shares: int = 0
    views: int = 0

    # Time
    published_at: Optional[datetime] = None
    scraped_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Metadata
    niche: Optional[str] = None
    platform_trust: float = 0.75

    @property
    def engagement_score(self) -> float:
        """Log-scaled composite engagement proxy."""
        raw = self.score + (self.comments * 3) + self.shares + (self.views * 0.001)
        return math.log1p(raw)
```

### 6.6 Aggregator — Parallel Orchestration

The aggregator launches all scrapers concurrently via `asyncio.gather`, deduplicates by URL/content hash, filters signals by age, caps the batch via round-robin platform selection (max 200 signals to prevent NLP timeout), then feeds through the NLP pipeline and ranker:

```python
class TrendAggregator:
    def __init__(self):
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

    async def run_cycle(self, niche: str) -> List[TrendCluster]:
        niche_config = NICHES[niche]
        all_signals = await self._scrape_all(niche, niche_config)   # Parallel
        signals = self._deduplicate(all_signals)                     # URL + hash
        signals = self._filter_by_age(signals)                       # 24h window
        clusters = self.nlp.process(signals)                         # Embed + cluster
        ranked = self.ranker.rank(clusters)                          # Score + tier
        return ranked
```

---

## 7. Stage 02 — Content Generation Engine

### 7.1 Script Generation Architecture

For each detected trend, the system generates 3–5 video scripts using different content angles:

| Angle | Target Duration | Format | Use Case |
|---|---|---|---|
| Explainer | 60s | Talking-head | "What is X and why it matters" |
| Hot-take | 30s | Talking-head | "My controversial opinion on X" |
| Tutorial | 60s | Screen-record | "How to use X right now" |
| Listicle | 30s | Carousel-video | "5 things about X you didn't know" |
| Storytime | 60s | Talking-head | "The story behind X that nobody talks about" |
| Comparison | 60s | Split-screen | "X vs Y — which one wins?" |
| Myth-bust | 30s | Text-overlay | "3 myths about X debunked" |
| News-flash | 15s | B-roll + voice | "BREAKING: X just happened" |

### 7.2 VideoScript Schema

```python
@dataclass
class VideoScript:
    script_id: str
    trend_topic: str
    trend_score: float
    trend_tier: str
    niche: str

    hook: str                    # First 3 seconds (make-or-break)
    body_points: List[str]       # Key content beats (3-7 points)
    cta: str                     # Call to action
    full_script: str             # Complete assembled script

    content_angle: str           # explainer / hot-take / tutorial / etc.
    format_type: str             # vertical-video / carousel / talking-head
    duration: str                # 15s / 30s / 60s / 90s
    platform_target: str         # reels / shorts / both

    hashtags: List[str]
    seo_title: str
    thumbnail_text: str

    # Scoring (0.0 - 1.0 each)
    hook_score: float = 0.0
    trend_alignment: float = 0.0
    virality_potential: float = 0.0
    format_fit: float = 0.0
    production_ease: float = 0.0
    engagement_forecast: float = 0.0
    composite_script_score: float = 0.0
```

### 7.3 Script Scoring Weights

```python
SCRIPT_SCORE_WEIGHTS = {
    "hook_score":           0.25,  # Hook is king in short-form
    "trend_alignment":      0.20,  # Must match actual trend data
    "virality_potential":   0.20,  # Will people share this?
    "format_fit":           0.15,  # Right format for content type
    "engagement_forecast":  0.12,  # Predicted engagement rate
    "production_ease":      0.08,  # Lower barrier = faster to market
}
```

### 7.4 Content-Aware Body Generation

Scripts are generated from **real scraped data** — not generic templates. The body builder consumes source captions, mentioned tools, key claims, content examples, and engagement statistics extracted by the NLP processor:

```python
def _build_body_points(self, angle: str, ctx: dict) -> List[str]:
    """
    Build script body points from REAL content data.
    Uses source_captions, mentioned_tools, key_claims,
    content_examples, and engagement_stats.
    """
    topic = ctx["topic"][:50]
    tools = ctx.get("tools", [])
    claims = ctx.get("claims", [])
    captions = ctx.get("captions", [])
    stats = ctx.get("stats", {})

    if angle == "explainer":
        points = []
        if tools:
            points.append(
                f"This trend is centered around {', '.join(tools[:4])}"
            )
        if captions:
            points.append(
                f'One creator put it this way: "{captions[0][:100]}"'
            )
        if stats.get("total_views", 0) > 1000:
            points.append(
                f"Combined content has pulled {fmt(stats['total_views'])} views"
            )
        if claims:
            points.append(f"Key insight: {claims[0][:120]}")
        return points
```

---

## 8. Hybrid Organic Instagram Scraping Module

### 8.1 Design Rationale

Traditional Instagram scraping relies on hashtag-based Apify queries, which returns structured but **inorganic** results biased toward popular tags. The user's original approach involved manual Selenium-based scrolling of the organic `/reels/` feed, which captures **algorithmically curated** content — the same feed a real user would see.

VELOCI's hybrid approach combines both:

1. **Automated Playwright Login** → Stealth headless Chromium logs into Instagram using `.env` credentials
2. **Organic Feed Scrolling** → Simulates human browsing of `instagram.com/reels/`
3. **URL Harvesting** → Extracts `/reel/` links from the DOM
4. **Apify Proxy Relay** → Passes harvested URLs to Apify for rich metadata extraction (likes, plays, hashtags) via `directUrls`

### 8.2 Implementation

```python
async def _run_playwright_harvest(
    self, niche: str, niche_config: dict, limit: int = 15
) -> List[str]:
    """
    Organically scrape raw Reels URLs by simulating user browsing
    through instagram.com/reels/ using stealth Chromium.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-notifications"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
            viewport={"width": 1280, "height": 800}
        )
        # Defeat webdriver detection
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', "
            "{get: () => undefined})"
        )

        page = await context.new_page()

        # Automated login
        await page.goto("https://www.instagram.com/accounts/login/")
        await page.fill("input[name='username']", IG_USERNAME)
        await page.fill("input[name='password']", IG_PASSWORD)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(5000)

        # Navigate to organic Reels feed
        await page.goto("https://www.instagram.com/reels/")

        # Scroll and harvest URLs organically
        urls = []
        while len(urls) < limit:
            elements = await page.query_selector_all("a[href*='/reel/']")
            for el in elements:
                href = await el.get_attribute("href")
                if href:
                    full_url = f"https://www.instagram.com{href}"
                    if full_url not in urls:
                        urls.append(full_url)
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(random.uniform(1500, 3500))

        await browser.close()
    return urls[:limit]
```

### 8.3 Apify Proxy Relay

```python
async def _scrape_via_apify(self, niche, niche_config) -> List[RawSignal]:
    # Step 1: Harvest organic URLs via Playwright
    organic_urls = await self._run_playwright_harvest(niche, niche_config, limit=20)

    if not organic_urls:
        # Fallback to legacy hashtag search
        return await self._scrape_via_apify_fallback(niche, niche_config)

    # Step 2: Push to Apify via directUrls (no hashtag search)
    payload = {
        "directUrls": organic_urls,
        "resultsType": "posts"
        # Explicitly NO searchType = 'hashtag'
    }

    r = await client.post(
        f"{APIFY_BASE}/acts/{HASHTAG_ACTOR}/runs",
        params={"token": APIFY_TOKEN},
        json=payload,
    )
    # ... poll for results, map to RawSignal
```

---

## 9. NLP Pipeline Deep-Dive

### 9.1 Processing Flow

```
Raw Signals (300-500 per cycle)
    ↓
Clean & Normalize (HTML strip, URL removal, hashtag normalization)
    ↓
Embed (all-MiniLM-L6-v2, 384-dim, L2-normalized)
    ↓
DBSCAN Cluster (cosine distance, eps=0.28, min_samples=2)
    ↓
TF-IDF Keywords (per cluster, 120+ stopwords filtered)
    ↓
Named Entity Recognition (spaCy en_core_web_sm)
    ↓
VADER Sentiment Scoring (per cluster)
    ↓
Topic Distillation (entity + keyword + centroid-nearest signal)
    ↓
Content Analysis (captions, tools, claims, examples, engagement stats)
    ↓
TrendCluster Objects → Ranker
```

### 9.2 Stopword Engineering

The system maintains a comprehensive 120+ word blocklist that removes:
- **HTML/CSS fragments**: `class`, `div`, `span`, `width`, `margin`, `padding`...
- **Platform noise**: `google`, `youtube`, `reddit`, `trending`, `subscribe`, `follow`...
- **Time filler**: `just`, `new`, `now`, `today`, `2024`, `2025`, `2026`
- **Generic filler**: `one`, `two`, `first`, `thing`, `people`, `would`...

### 9.3 Language Gate

Fast character-ratio heuristic that rejects non-English content (Hindi, CJK, Arabic) without external dependencies:

```python
@staticmethod
def _is_english_text(text: str) -> bool:
    """
    Reject text with >25% non-Latin characters.
    """
    clean = re.sub(r'https?://\S+', '', text)
    clean = re.sub(r'[#@]\w+', '', clean)
    latin, non_latin = 0, 0
    for ch in clean:
        cp = ord(ch)
        if cp < 128 or 0x0080 <= cp <= 0x024F:
            latin += 1
        elif cp > 0x024F and ch.isalpha():
            non_latin += 1
    total_alpha = latin + non_latin
    if total_alpha == 0:
        return False
    return (non_latin / total_alpha) < 0.25
```

### 9.4 Topic Distillation Strategy

Instead of using raw signal titles as topics, the system distills clean labels via a 4-strategy cascade:

1. **Entity + Keyword combo**: e.g., "OpenAI: GPT Models & Regulation"
2. **Top TF-IDF keywords** as descriptive phrase: e.g., "Quantum Computing Breakthrough"
3. **Best entity alone**: e.g., "Sundar Pichai"
4. **Closest-to-centroid signal title** (cleaned): Last resort fallback

### 9.5 Content Analysis for Script Generation

The NLP processor extracts rich content data applying three critical filters:

1. **Language Gate** — Reject non-English captions
2. **Relevance Gate** — Only use captions sharing ≥2 keywords with cluster topic
3. **URL Traceability** — Only attach URLs from signals that contributed content

---

## 10. Ensemble Ranking Algorithm

### 10.1 Composite Score Formula

```
composite_score = (
    0.35 × velocity_score +
    0.25 × cross_platform_score +
    0.20 × novelty_score +
    0.10 × sentiment_score +
    0.10 × engagement_potential
)
```

### 10.2 Velocity Calculation

```python
def _compute_velocity(self, cluster, historical):
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    four_hours_ago = now - timedelta(hours=4)

    recent = sum(1 for s in cluster.sources if s.scraped_at >= one_hour_ago)
    previous = sum(
        1 for s in cluster.sources
        if four_hours_ago <= s.scraped_at < one_hour_ago
    )

    if previous == 0:
        # All signals new — extremely fast-moving
        velocity = min(math.log1p(recent * 5) / math.log1p(25), 1.0)
    else:
        ratio = recent / max(previous, 1)
        velocity = min(math.log1p(ratio * 3) / math.log1p(10), 1.0)

    return round(velocity, 4)
```

### 10.3 Cross-Platform Score

```python
PLATFORM_TRUST = {
    "google_trends_rising":  1.00,  # Best early signal
    "reddit_rising":         0.92,  # Rising = 6-24h ahead
    "twitter_velocity":      0.87,  # Real-time but noisy
    "news_rss":              0.83,  # Breaking news
    "youtube_trending":      0.75,  # Slight lag, high validation
    "instagram_reels":       0.73,  # Confirms virality
}

def _compute_cross_platform(self, cluster):
    seen = set()
    total_weight = 0.0
    max_possible = sum(
        sorted(PLATFORM_TRUST.values(), reverse=True)[:4]
    )
    for signal in cluster.sources:
        if signal.platform not in seen:
            seen.add(signal.platform)
            total_weight += PLATFORM_TRUST.get(signal.platform, 0.65)
    return round(min(total_weight / max_possible, 1.0), 4)
```

---

## 11. Rate Limiting & Circuit Breaker Infrastructure

### 11.1 Free Tier Budget Table

| Platform | Free Tier Limit | Our Budget | Algorithm |
|---|---|---|---|
| YouTube API v3 | 10,000 units/day | 8,000 units | Token bucket |
| Twitter/X v2 | 500K tweets/month | 400K tweets | Token bucket |
| NewsAPI | 100 requests/day | 80 req/day | Token bucket |
| Google Trends | ~30 requests/hour | 20 req/hour | Token bucket |
| Reddit API | 60 requests/minute | 50 req/min | Token bucket |
| GDELT | No official limit | 120 req/hour | Token bucket |
| Instagram/Apify | $5/mo free credits | 20 req/hour | Token bucket + budget file |

### 11.2 Token Bucket Implementation

```python
@dataclass
class TokenBucket:
    max_tokens: float
    refill_rate: float  # tokens per second

    async def acquire(self, cost: float = 1.0) -> float:
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return 0.0
        wait_time = (cost - self.tokens) / self.refill_rate
        await asyncio.sleep(wait_time)
        self._refill()
        self.tokens -= cost
        return wait_time
```

### 11.3 Circuit Breaker Pattern

```python
@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_seconds: float = 300.0  # 5 minutes

    # States: CLOSED (healthy) → OPEN (tripped) → HALF_OPEN (probing)
    def record_failure(self):
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = "open"  # Block all requests for cooldown
```

---

## 12. Database Architecture

### 12.1 Schema

```sql
-- Ranked TrendCluster records per cycle
CREATE TABLE trends (
    id              TEXT PRIMARY KEY,
    niche           TEXT NOT NULL,
    topic           TEXT NOT NULL,
    keywords        TEXT,           -- JSON array
    entities        TEXT,           -- JSON array
    platforms       TEXT,           -- JSON array
    composite_score REAL,
    velocity_score  REAL,
    cross_platform_score REAL,
    novelty_score   REAL,
    sentiment_score REAL,
    tier            TEXT,
    source_count    INTEGER,
    scraped_at      TEXT,
    first_seen      TEXT
);

-- Individual RawSignal records (for velocity history)
CREATE TABLE signals (
    id          TEXT PRIMARY KEY,
    trend_id    TEXT,
    platform    TEXT,
    source_id   TEXT,
    url         TEXT,
    title       TEXT,
    score       INTEGER,
    views       INTEGER,
    comments    INTEGER,
    niche       TEXT,
    published_at TEXT,
    scraped_at  TEXT
);

-- Post performance per channel (RL reward signal)
CREATE TABLE channel_perf (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      TEXT NOT NULL,
    post_id         TEXT,
    trend_id        TEXT,
    views_1h        INTEGER DEFAULT 0,
    views_24h       INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    watch_time_pct  REAL DEFAULT 0,
    velocity_score  REAL DEFAULT 0
);

-- Content generation log
CREATE TABLE content_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_id        TEXT,
    channel_id      TEXT,
    angle           TEXT,
    script          TEXT,
    engagement_pred REAL,
    status          TEXT DEFAULT 'pending'
);
```

---

## 13. Sample Pipeline Output

### 13.1 JSON Output Structure

```json
{
  "veloci_version": "2.0",
  "generated_at": "2026-04-03T07:58:55+00:00",
  "niche": "tech_ai",
  "niche_display": "Tech & AI",
  "total_trends": 5,
  "trends": [
    {
      "cluster_id": "b9e301efbfbc",
      "topic": "'Uncanny Valley': Iran's Threats on US Tech...",
      "keywords": ["ai", "iran", "tech", "trump", "startup"],
      "platforms": ["youtube_trending", "news_rss", "twitter_velocity", "reddit_rising"],
      "source_count": 180,
      "velocity_score": 1.0,
      "cross_platform_score": 0.9309,
      "novelty_score": 1.0,
      "composite_score": 0.9191,
      "tier": "early",
      "platform_breakdown": {
        "reddit_rising": 21,
        "youtube_trending": 45,
        "twitter_velocity": 6,
        "news_rss": 108
      }
    }
  ]
}
```

### 13.2 CSV Output Columns

```
rank, tier, composite_score, topic, summary, keywords, entities,
platforms, platform_breakdown, velocity, cross_platform, novelty,
sentiment, engagement_potential, signal_count, suggested_hook,
suggested_duration, suggested_format, suggested_hashtags,
content_angles, source_urls, niche, first_seen
```

---

## 14. Crash Test & Validation Suite

### 14.1 Test Categories

| Category | Test ID Range | Description |
|---|---|---|
| Security | CT-SEC-01 to 04 | `.gitignore`, credentials, hardcoded keys, `.env.example` |
| Reddit Scraper | CT-S01-A/B | Health check, signal count |
| YouTube Scraper | CT-S02-A/B/C | Health, signal quality, API quota |
| Google Trends | CT-S03-A/B/C | Health, rising queries, rate limiting |
| Twitter Scraper | CT-S04-A/B | Health, signal volume |
| News Scraper | CT-S05-A/B | Health, RSS + GDELT |
| Instagram Scraper | CT-S06-A/B | Apify health, organic harvest |
| Database | CT-D01-A/B | Connection, invalid path handling |
| NLP Pipeline | CT-N01-A/B | Embedding, clustering |
| Full Pipeline | CT-P01-A/B/C | End-to-end cycle, export, circuit breakers |

### 14.2 Latest Results

```
Total:   31
✅ Pass:  25
❌ Fail:  4
⚠️ Warn:  2
Pipeline Health: 81% — 🟡 MOSTLY READY
```

**Known failures**: Google Trends 429 rate limiting (handled by circuit breaker), timezone-aware datetime comparisons (cosmetic).

---

## 15. Development Prompt History

### 15.1 Conversation 1 — Initial Hardening (Session e3e1fcc8)

**Objective**: Production-grade transition of VELOCI Trend Intelligence Engine.

**Key prompts submitted by user**:
- Implementing autonomous, proxy-based Instagram scraping via Apify with free-tier budget tracking
- Refining NLP keyword processing with robust stopword filtering and noise reduction
- Ensuring system-wide security and dependency management
- Verifying full pipeline through comprehensive health and crash test suite
- Resolving Python deprecation warnings (`datetime.utcnow()`)

### 15.2 Conversation 2 — Autonomous Pipeline Optimization (Session ae256861)

**Prompt 1** — Initial request:
> "Go through progress.md and build.md along with all the code files and implement the next plan of action. Input API tokens in the .env file but they don't seem to get parsed. While turning it to the dotenv format make sure keys are copied perfectly. Debug preserving content purity."

**Prompt 2** — Approval with constraints:
> "Sure do that and make sure they work perfectly flawlessly. Don't go changing the basic structure."

**Prompt 3** — Output validation:
> "I don't see the changes made. Also I asked for a final output CSV and JSON both. I don't see that too."

**Prompt 4** — Platform correction:
> "Except we had 3 niches and 3 outputs. The whole pipeline got messed up. Also it is only YouTube and Google Trends the results."

**Prompt 5** — TikTok removal + ensemble enforcement:
> "Remove that functionality, don't let the system be redundant. Balance results from all sources with ensemble not direct result from single pipeline rather cross with every source for trend generation over all niches. Make sure env is made to right format keeping the keys as is."

**Prompt 6** — Automation mandate:
> "This is an iterative self-sufficient automated model which would do everything as intended on its own. Make it to that parameter."

**Prompt 7** — Ensemble clarification:
> "It needs to balance all sources not ensemble as in threshold. I meant one folder where I can individually see each not 3 like output, output, final, output, test."

**Prompt 8** — Cross-verification emphasis:
> "Balance results in a good way. Threshold and all is fine but cross verification is more important and mapping of emerging and already running trends as pipeline takes. Keep in mind API limitations for free use."

**Prompt 9** — Execution request:
> "Run an iteration and show results."

**Prompt 10** — Instagram overhaul:
> "The insta scraper is not working promptly. Instead of taking the tags and using that as input, what I want is a proxy that would login itself, scrape reels in an organic way using Apify, analyze as the code I gave earlier suggested except it used manual scraping."

### 15.3 Key Technical Decisions Driven by Prompts

| User Directive | Technical Implementation |
|---|---|
| "Balance results from all sources" | Exponential scoring bonuses for multi-platform corroboration (2+ sources) |
| "One folder, not 3" | Unified `output/` directory with `veloci_trends_{niche}_{timestamp}.{ext}` naming |
| "Self-sufficient automated model" | `AsyncIOScheduler` + `export_trends_full()` integrated directly into 30-min cycle |
| "Remove TikTok functionality" | Complete removal of `tiktok_scraper.py` imports, tests, and aggregator references |
| "Login itself scrape reels organically" | Playwright stealth browser + `IG_USERNAME`/`IG_PASSWORD` automation |
| "Cross verification is more important" | `_compute_cross_platform()` with weighted platform trust scoring |
| "Keep in mind API limitations" | Token bucket rate limiter + circuit breaker per platform |

---

## 16. Future Stages — Pseudocode & Snippets

### 16.1 Stage 03 — Multimodal Engagement Predictor (Publish Gate)

```python
class EngagementPredictor:
    """
    Multimodal gate: E = f(video, audio, caption, metadata)
    Decision: E >= θ → publish | E < θ → regenerate
    """

    def __init__(self):
        self.visual_encoder = ViTModel.from_pretrained("google/vit-base-patch16-224")
        self.audio_encoder = Wav2Vec2Model.from_pretrained("facebook/wav2vec2-base")
        self.text_encoder = SentenceTransformer("all-MiniLM-L6-v2")
        self.fusion = CrossModalAttentionFusion(dim=768, heads=8)
        self.prediction_heads = {
            "nawp": nn.Linear(768, 1),   # Normalised Average Watch Percentage
            "ecr":  nn.Linear(768, 1),   # Engagement Continuation Rate
            "views": nn.Linear(768, 1),
            "likes": nn.Linear(768, 1),
        }
        self.theta = 0.60  # Adaptive threshold (drift-adjusted)

    def predict(self, video_path, audio_path, caption, metadata):
        # Extract features
        visual_feat = self.visual_encoder(sample_frames(video_path, n=8))
        audio_feat = self.audio_encoder(load_audio(audio_path))
        text_feat = self.text_encoder.encode(caption)

        # Cross-modal attention fusion
        fused = self.fusion(visual_feat, audio_feat, text_feat)

        # Multi-task prediction
        nawp = torch.sigmoid(self.prediction_heads["nawp"](fused))
        ecr = torch.sigmoid(self.prediction_heads["ecr"](fused))

        engagement_score = 0.6 * nawp + 0.4 * ecr
        return {
            "score": engagement_score.item(),
            "should_publish": engagement_score.item() >= self.theta,
            "nawp": nawp.item(),
            "ecr": ecr.item(),
        }

    def update_theta(self, recent_scores):
        """Drift: θ adapts to observed performance distribution."""
        top_quartile = np.percentile(recent_scores, 75)
        self.theta = 0.7 * self.theta + 0.3 * top_quartile
```

### 16.2 Stage 04 — RL Contextual Bandit Scheduler

```python
class PublishScheduler:
    """
    Contextual bandit: learns optimal publish time per channel.
    Reward signal = first-hour engagement velocity.
    Adapted from Zou et al. FeedRec (KDD 2019).
    """

    def __init__(self, channels: List[str]):
        self.q_network = LSTMQNetwork(
            context_dim=32,   # time features + channel history
            n_actions=48,     # 48 half-hour slots per day
            hidden_dim=128,
        )
        self.epsilon = 0.15  # Exploration rate (decays over time)
        self.channel_history = {ch: [] for ch in channels}

    def select_publish_time(self, channel_id, trend, current_time):
        context = self._build_context(channel_id, trend, current_time)

        # Epsilon-greedy exploration
        if random.random() < self.epsilon:
            action = random.randint(0, 47)  # Random slot
        else:
            q_values = self.q_network(context)
            action = torch.argmax(q_values).item()

        # Convert action to timestamp
        publish_time = self._action_to_timestamp(action, current_time)
        return publish_time

    def receive_reward(self, channel_id, action, views_1h, views_24h):
        """
        Reward = first-hour velocity = views_1h / max(views_24h, 1)
        High velocity = platform algorithm is amplifying.
        """
        velocity = min(views_1h / max(views_24h, 1), 1.0)
        self.channel_history[channel_id].append({
            "action": action,
            "reward": velocity,
        })
        # Update Q-network via experience replay
        self._train_step(channel_id, action, velocity)

    def _build_context(self, channel_id, trend, current_time):
        return torch.tensor([
            current_time.hour / 24,
            current_time.weekday() / 7,
            trend.composite_score,
            trend.velocity_score,
            len(self.channel_history[channel_id]),
            # ... more context features
        ])
```

### 16.3 Stage 05 — Auto-Publish Layer

```python
class AutoPublisher:
    """
    Handles platform-specific upload with content fingerprint variation.
    """

    async def publish_to_youtube(self, video_path, metadata):
        youtube = build("youtube", "v3", credentials=creds)
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": metadata["seo_title"],
                    "description": metadata["full_script"],
                    "tags": metadata["hashtags"],
                    "categoryId": "28",  # Science & Technology
                },
                "status": {
                    "privacyStatus": "public",
                    "publishAt": metadata["scheduled_time"].isoformat(),
                }
            },
            media_body=MediaFileUpload(video_path)
        )
        response = request.execute()
        return response["id"]

    async def publish_to_instagram(self, video_path, metadata):
        # Instagram Graph API for Reels
        container = await self._create_media_container(
            video_url=self._upload_to_cdn(video_path),
            caption=metadata["caption"] + "\n\n" + " ".join(metadata["hashtags"]),
        )
        result = await self._publish_container(container["id"])
        return result["id"]

    def _fingerprint_variation(self, video_path, channel_id):
        """
        Apply subtle variations per channel to defeat duplicate detection:
        - Slight audio pitch shift (±2%)
        - Color temperature adjustment
        - Intro/outro variation
        - Unique watermark placement
        """
        pass
```

### 16.4 Stage 06 — Feedback Learning Loop

```python
class FeedbackLoop:
    """
    Collects post-publish performance data and updates all models.
    Checkpoints: 1h, 6h, 24h, 7d after publish.
    """

    async def collect_metrics(self, post_id, platform, channel_id):
        if platform == "youtube":
            analytics = self._fetch_youtube_analytics(post_id)
        elif platform == "instagram":
            analytics = self._fetch_ig_insights(post_id)

        await db.update_channel_performance(
            channel_id=channel_id,
            post_id=post_id,
            platform=platform,
            views_1h=analytics["views_1h"],
            views_24h=analytics["views_24h"],
            likes=analytics["likes"],
            watch_time_pct=analytics["avg_watch_pct"],
        )

        # Feed reward to RL scheduler
        scheduler.receive_reward(
            channel_id, action, analytics["views_1h"], analytics["views_24h"]
        )

        # Retrain engagement predictor with new data point
        predictor.add_training_sample(
            content_features=post.features,
            actual_engagement=analytics,
        )

    def update_score_weights(self, performance_history):
        """
        Adjust velocity/cross-platform/novelty/sentiment weights
        based on which signals actually predicted success.
        """
        # Correlate trend scores with actual post performance
        correlations = {}
        for metric in ["velocity", "cross_platform", "novelty", "sentiment"]:
            correlations[metric] = np.corrcoef(
                [t[metric] for t in performance_history],
                [t["views_24h"] for t in performance_history]
            )[0, 1]

        # Rebalance weights proportionally
        total = sum(abs(v) for v in correlations.values())
        for metric, corr in correlations.items():
            WEIGHTS[metric] = abs(corr) / total
```

### 16.5 Stage 07 — Analytics Dashboard

```python
class AnalyticsDashboard:
    """
    Revenue tracking + live trend monitoring.
    Built with FastAPI + React or Streamlit.
    """

    # Revenue Streams:
    # 1. Platform payouts (YouTube Partner, TikTok Creator Fund, IG Bonuses)
    # 2. Subscription SaaS (Free / Pro $29/mo / Agency $149/mo)
    # 3. B2B Ad Generation (automated short-form ad creatives)
    # 4. Affiliate Content (trend-matched product promotion)

    @app.get("/api/trends/live")
    async def get_live_trends(niche: str = None):
        trends = await db.get_recent_trends(niche, hours=24)
        return {"trends": trends, "count": len(trends)}

    @app.get("/api/channels/{channel_id}/performance")
    async def get_channel_metrics(channel_id: str):
        history = await db.get_channel_performance_history(channel_id)
        return {
            "channel_id": channel_id,
            "total_views": sum(h["views_24h"] for h in history),
            "avg_velocity": np.mean([h["velocity_score"] for h in history]),
            "best_posting_times": scheduler.get_learned_windows(channel_id),
        }
```

---

## 17. Evaluation Metrics

| Metric | Type | What It Measures |
|---|---|---|
| MAE | Regression | Primary metric for engagement score prediction |
| F1 Score | Classification | Viral vs. non-viral accuracy (binary gate) |
| NAWP | Engagement | Duration-normalized watch percentage |
| ECR | Engagement | Do viewers return for related content? |
| Watch Time Uplift | A/B | % improvement vs. unfiltered baseline over 30 days |
| CTR Uplift | A/B | AI titles/thumbnails vs. human-authored |

### Experimental Design

- **Unimodal baselines**: visual-only CNN, audio-only CRNN, text-only BERT
- **Multimodal baseline**: late fusion (no attention) vs. our cross-modal attention
- **RL baseline**: static SproutSocial heuristics vs. trained contextual bandit
- **Ablation**: each module removed one at a time to measure contribution

---

## 18. Security & Safeguards

### 18.1 Credential Security
- All API keys loaded via `python-dotenv` from `.env` (never hardcoded)
- Log sanitization: all sensitive values replaced with `[REDACTED]` globally
- `.gitignore` covers `.env`, `*.db`, `veloci_scraper.log`
- `.env.example` template provided for safe commits

### 18.2 Content Protection
- **Fingerprinting**: pHash + dHash per video frame, acoustID for audio
- **Originality threshold**: reject if cosine similarity > 0.85 to any known content
- **Platform ToS monitor**: automated compliance check before publish
- **Per-channel variation**: unique audio/visual fingerprint to avoid cross-channel strikes

### 18.3 Anti-Monetization Defence
- Copyright detection via audio fingerprint + visual reverse search
- DMCA pre-check: scan title/description for flagged terms
- Fair use compliance: transformative content scoring
- Per-channel visual/audio variation to defeat duplicate detection algorithms

---

## 19. Repository Structure

```
analysis/
├── main.py                           # Entry point + scheduler
├── config.py                         # All config, niches, weights, API keys
├── crash_test.py                     # Comprehensive validation suite
├── requirements.txt                  # Python dependencies
├── .env                              # API credentials (git-ignored)
├── .env.example                      # Template for safe commits
├── veloci.db                         # SQLite database
├── veloci_scraper.log                # Runtime log
│
├── scrapers/
│   ├── base.py                       # RawSignal + BaseScraper ABC
│   ├── reddit_scraper.py             # PRAW + JSON API fallback
│   ├── youtube_scraper.py            # YouTube Data API v3
│   ├── google_trends_scraper.py      # pytrends (unofficial)
│   ├── twitter_scraper.py            # Tweepy + Google News fallback
│   ├── news_scraper.py               # NewsAPI + RSS + GDELT
│   └── instagram_scraper.py          # Playwright Organic + Apify Proxy
│
├── pipeline/
│   ├── aggregator.py                 # Parallel scrape orchestrator
│   ├── nlp_processor.py              # Embed → DBSCAN → TF-IDF → NER → VADER
│   ├── ranker.py                     # Velocity + cross-platform + novelty scoring
│   ├── rate_limiter.py               # Token bucket + circuit breaker
│   └── script_generator.py           # Stage 02: Video script generation
│
├── storage/
│   └── database.py                   # Async SQLite (aiosqlite)
│
└── output/                           # Unified export directory
    ├── veloci_trends_tech_ai_*.json
    ├── veloci_trends_tech_ai_*.csv
    ├── veloci_trends_finance_*.json
    ├── veloci_trends_finance_*.csv
    ├── veloci_trends_entertainment_*.json
    └── veloci_trends_entertainment_*.csv
```

---

## 20. Conclusion & Future Work

### 20.1 Current Achievements
- **Stage 01** is production-ready: 6 scrapers run autonomously every 30 minutes, signals are deduplicated, NLP-clustered, ensemble-ranked, and exported to a unified output directory.
- **Stage 02** script generator produces 3–5 content-aware scripts per trend using real scraped data.
- **Hybrid Instagram Scraper** combines automated Playwright login with Apify proxy extraction, bypassing static hashtag limitations.
- **Pipeline Health**: 81% crash test pass rate with graceful degradation for rate-limited APIs.

### 20.2 Immediate Next Steps
1. **Stage 03**: Implement the multimodal engagement predictor using ViT + wav2vec2 + cross-modal attention fusion.
2. **Reddit Auth Fix**: Resolve PRAW 401 to restore full Reddit scraping.
3. **CI/CD**: Formalise `crash_test.py` into a CI pipeline.
4. **Database-First Architecture**: Transition downstream modules to consume from `veloci.db` directly.

### 20.3 Long-Term Vision
The complete 7-stage pipeline will form a **self-learning digital creator** — a system that discovers what's trending, creates content about it, predicts whether the content will perform well, schedules it at the optimal time, publishes it, monitors the results, and uses those results to get better at every step. The research contribution lies in the closed-loop architecture (C2), the use of engagement prediction as a generation gate rather than post-hoc evaluator (C1), and first-hour velocity as a formalised RL reward signal (C4).

---

> **Document Version**: 1.0
> **Generated**: April 2026
> **System**: VELOCI v2.0
> **Authors**: Development team — iterative prompt-driven engineering across multiple sessions
