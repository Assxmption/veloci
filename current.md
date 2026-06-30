# VELOCI Trend Engine — Ground Reality Status
> Last updated: 2026-04-02 02:00 IST

---

## User Prompts (Chronological)

1. **Optimise code, check output, learning loop, CSV export**
   - Asked to optimise the codebase, verify learning loop viability, add CSV export

2. **Safeguard credentials, real keys protection, Reddit API details**
   - Provided Reddit API keys (client ID, secret, user agent)
   - Asked for production-grade credential protection
   - Asked whether models should be in separate folders

3. **SpaCy setup, free-tier guidance for Twitter/TikTok, India workaround**
   - Requested free-tier usage for all APIs
   - Asked for TikTok workaround (not natively accessible from India)
   - Wanted robust security

4. **Full crash test, show trend output**
   - Asked for end-to-end pipeline run with real output
   - Questioned whether results were from personal searches vs actual trends

5. **Fix red errors, make production ready**
   - Wanted lint errors resolved
   - Asked for Indian news sources as workaround
   - Noted output was too tech/finance heavy, wanted entertainment coverage
   - Asked for Reddit API to be called properly with provided keys

6. **Add proxy for TikTok**
   - Requested proxy-based TikTok scraping

7. **Proper JSON/CSV output with scoring breakdown, niche filtering**
   - Wanted score calculation explained (which platform, what niche)
   - Asked to add/remove final parameters for video generation pipeline
   - Wanted niche screening (remove lifestyle, travel etc)
   - Shared friend's Instagram scraping code (Selenium-based) to ensemble

8. **Stopwords filtering, Apify API for Instagram, autonomous scraping**
   - Provided Apify API token
   - Wanted autonomous, anonymous Instagram scraping (no manual feeds)
   - Asked for proper stopword filtering in NLP keywords
   - Wanted requirements.txt for collaborator deployment

9. **Full health + output run with Instagram scraper**
   - Wanted flawless Insta scraping with Apify token
   - Asked for Reddit API status update
   - Requested Apify free-tier budget limits

---

## What's Actually Working ✅

| Component | Status | Details |
|-----------|--------|---------|
| **Reddit (JSON fallback)** | ✅ Healthy | 300+ signals/niche via `reddit.com/.json` API. PRAW auth fails (401) due to Reddit's "Responsible Builder" policy — fallback is robust |
| **YouTube Trending** | ✅ Healthy | ~107 signals/run via RSS |
| **Google Trends** | ✅ Healthy | ~100 signals via pytrends |
| **Twitter/Nitter** | ✅ Healthy | ~50 signals via RSS fallback |
| **News RSS** | ✅ Healthy | ~242 signals from global feeds |
| **Instagram (Apify proxy)** | ✅ Fixed | `apify~instagram-scraper` returned **120 reels** on last successful run. Actor ID `~` separator was the blocker (was using `/`) |
| **Instagram (seed fallback)** | ✅ Healthy | 6 signals/niche from built-in hashtag corpus when Apify unavailable |
| **NLP Pipeline** | ✅ Working | Stopwords (120+), HTML/CSS stripping, hashtag validation all active |
| **Ranker** | ✅ Working | 5-weight scoring (velocity, cross-platform, novelty, engagement, recency) |
| **JSON + CSV Export** | ✅ Working | Dual export with full scoring breakdown |
| **Budget Tracker** | ✅ Working | `.apify_budget.json` tracks 50 runs/month limit |
| **Security** | ✅ Working | `.env` for all keys, `_SanitizeFilter` redacts from logs, `.gitignore` covers secrets |
| **requirements.txt** | ✅ Created | All deps pinned for collaborator install |

---

## What's Broken / Blocked ❌

| Issue | Root Cause | Impact |
|-------|-----------|--------|
| **NLP hangs on large batches** | Sentence-transformer embedding computes on CPU for 765+ signals — takes 30+ min, effectively hangs | Pipeline stalls after scraping succeeds. **FIX APPLIED**: Added 200-signal cap in aggregator (sorts by engagement, keeps top 200) — **NOT YET TESTED** |
| **Reddit PRAW auth** | Reddit's "Responsible Builder" policy returns 401 for new apps | No impact — JSON fallback works perfectly. Not worth pursuing until Reddit approves the app |
| **Lint errors (Pyre2)** | ~100+ false-positive type errors from dynamic typing (`Counter`, `list.__getitem__` with slices, missing imports for installed packages) | **Zero runtime impact**. These are static analyser noise, not code bugs. All modules import and run correctly |

---

## What Was The Holdup

### The Apify Saga (biggest time sink)
1. **Wrong actor IDs**: Initially used `apify/instagram-hashtag-scraper` — doesn't exist on Apify Store
2. **Wrong URL separator**: Fixed to `apify/instagram-scraper` but Apify API uses `~` not `/` in URLs → got 404s
3. **Final fix**: `apify~instagram-scraper` with `directUrls` payload → **120 reels returned**
4. **New problem**: 120 Instagram + 300 Reddit + 100 Google Trends + 107 YouTube + 50 Twitter + 242 News = **932 signals** → NLP embedding step hung for 1.5 hours on CPU

### The NLP Timeout
- Previous runs had ~80 signals (with seed Instagram fallback) → finished in 50s
- With real Apify data: 765 signals after dedup → sentence-transformers can't compute embeddings for that many on CPU in reasonable time
- **Fix applied**: Cap at 200 top signals (sorted by engagement score) before NLP processing
- **Status**: Fix is in code but untested

---

## Last Successful Output (before Apify fix)

```
TECH & AI — 9 trends ranked
Top score: 0.934 — "This AI is Getting Scary" (reddit + news + youtube)
#2: 0.755 — "OpenAI $122B Round" (reddit)
#3: 0.670 — "#coding trending on Instagram" (instagram fallback)
#4: 0.656 — "Claude Code leak is overrated" (reddit)
...
```

Pipeline ran in ~53s with ~80 signals. Clean exit.

---

## Apify Data Schema (from your pasted output)

The raw Apify `instagram-scraper` returns rich data per post:

- `caption` — full post text with hashtags
- `commentsCount`, `likesCount` — engagement metrics
- `videoPlayCount`, `videoViewCount` — video-specific metrics
- `displayUrl` — thumbnail
- `videoUrl` / `audioUrl` — media URLs
- `timestamp` — post time
- `type` — Image / Video / Sidecar
- `shortCode` — IG post ID
- `taggedUsers[]` — tagged accounts with follower data
- `childPosts[]` — carousel slides
- `alt` — accessibility text (often AI-generated description)
- `firstComment` — top comment

**Key fields we're currently extracting**: caption, likesCount, commentsCount, videoPlayCount, hashtags (parsed from caption), timestamp, shortCode

**Fields we could use but don't yet**: taggedUsers (influencer mapping), videoViewCount (better engagement calc), alt text (content classification), childPosts count (carousel depth)

---

## File Structure

```
analysis/
├── .env                    # Real API keys (gitignored)
├── .env.example            # Template for collaborators
├── .gitignore              # Protects secrets
├── requirements.txt        # Pinned dependencies
├── config.py               # Central config, niches, trust weights
├── main.py                 # Entry point (--once / --schedule)
├── crash_test.py           # Health check suite
├── scrapers/
│   ├── base.py             # RawSignal schema + BaseScraper
│   ├── reddit_scraper.py   # PRAW + JSON fallback
│   ├── youtube_scraper.py  # RSS trending
│   ├── google_trends_scraper.py
│   ├── twitter_scraper.py  # Nitter RSS fallback
│   ├── news_scraper.py     # Multi-feed RSS
│   └── instagram_scraper.py # Apify proxy + seed fallback
├── pipeline/
│   ├── aggregator.py       # Orchestrator (scrape → NLP → rank → export)
│   ├── nlp_processor.py    # Embeddings, DBSCAN clustering, keyword extraction
│   ├── ranker.py           # 5-weight scoring formula
│   └── rate_limiter.py     # Per-platform rate limiting + circuit breaker
├── storage/
│   └── __init__.py
└── output/                 # Generated JSON/CSV exports
```

---

## Next Steps (Priority Order)

1. **Test the 200-signal cap** — run pipeline, verify it completes in <2min
2. **Improve Apify→RawSignal mapping** — use `videoViewCount`, `videoPlayCount` for better engagement scoring
3. **Validate niche filtering** — ensure entertainment/finance trends aren't all tech-dominated
4. **Full multi-niche run** — tech_ai + finance + entertainment in one cycle
5. **Move to Stage 02** — content generation pipeline (scripts, captions, hashtags for posting)
