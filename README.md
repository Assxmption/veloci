<div align="center">

```
 ██╗   ██╗███████╗██╗      ██████╗  ██████╗██╗
 ██║   ██║██╔════╝██║     ██╔═══██╗██╔════╝██║
 ██║   ██║█████╗  ██║     ██║   ██║██║     ██║
 ╚██╗ ██╔╝██╔══╝  ██║     ██║   ██║██║     ██║
  ╚████╔╝ ███████╗███████╗╚██████╔╝╚██████╗██║
   ╚═══╝  ╚══════╝╚══════╝ ╚═════╝  ╚═════╝╚═╝
```

**Trend Intelligence Engine · Autonomous UGC Pipeline · Stages 01 & 02**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen?style=flat-square)]()
[![Made with](https://img.shields.io/badge/Made%20with-caffeine%20%26%20conviction-orange?style=flat-square)]()

*Scrape → Cluster → Score → Script. Fully automated. Zero LLMs required.*

</div>

---

## The one-line pitch

> VELOCI watches 8 platforms simultaneously, spots what's about to blow up **12–72 hours before it peaks**, and auto-generates ranked video scripts for it — so you're always the creator who posted first, not the one playing catch-up.

This isn't a trend dashboard. It's a signal intelligence system that outputs **content-ready scripts** directly into your production queue.

---

## Why this exists

Every content creator faces the same problem: by the time you *notice* something is trending, it already is. You're not early — you're noise.

The insight that drove VELOCI:

- Reddit **RISING** posts (not HOT) show velocity, not popularity
- Google Trends **RELATED RISING** queries hit breakout (5000%+ growth) 24–72h before a topic dominates YouTube search
- GDELT covers 100+ languages — a launch in Korea surfaces in English feeds hours later

**Lead time is the only moat in content creation.** VELOCI is that moat.

---

## What's built (right now)

```
Stage 01: Trend Intelligence    ██████████ DONE
Stage 02: Script Generation     ██████████ DONE
Stage 03: Engagement Predictor  ░░░░░░░░░░ NEXT
Stage 04: RL Publish Scheduler  ░░░░░░░░░░ PLANNED
Stage 05: Auto-Publish Layer    ░░░░░░░░░░ PLANNED
Stage 06: Feedback Loop         ░░░░░░░░░░ PLANNED
Stage 07: Analytics Dashboard   ░░░░░░░░░░ PLANNED
```

---

## The pipeline (how it actually works)

```
                    ┌─────────────────────────────────────┐
                    │          VELOCI ENGINE v2.0          │
                    └─────────────────────────────────────┘

  INPUT SOURCES                  NLP CORE                    OUTPUT
  ─────────────                  ────────                    ──────

  Reddit RISING  ──┐
  YouTube Trends ──┤   ┌─────────────────────────┐
  Google Trends  ──┤   │ 1. Clean & normalize     │   ┌──────────────────┐
  Twitter/X      ──┼──▶│ 2. Semantic embed 384-d  │──▶│  TrendCluster[]  │
  NewsAPI + RSS  ──┤   │ 3. DBSCAN cluster        │   │  - topic         │
  GDELT          ──┤   │ 4. TF-IDF keywords       │   │  - score 0-1     │
  Instagram/Apify──┘   │ 5. NER entities          │   │  - tier (early→) │
                       │ 6. VADER sentiment        │   │  - platforms[]   │
                       └─────────────────────────┘   │  - angles[]      │
                                                       └──────────────────┘
                                                                │
                              ┌─────────────────────────────────┘
                              ▼
                   ┌────────────────────┐
                   │   RANKER           │    Composite score =
                   │   velocity ×0.35   │    weighted(velocity,
                   │   cross-platform   │    cross-platform,
                   │   ×0.25           │    novelty, sentiment,
                   │   novelty ×0.20   │    engagement)
                   │   sentiment ×0.10  │
                   │   engagement ×0.10 │
                   └────────────────────┘
                              │
                              ▼
                   ┌────────────────────────────────────────────┐
                   │         SCRIPT GENERATOR (Stage 02)         │
                   │                                            │
                   │  Per trend × 4 angles:                     │
                   │  ├── Explainer   "What is X and why now"   │
                   │  ├── Hot-take    "My controversial take"    │
                   │  ├── Tutorial    "How to use X right now"   │
                   │  ├── Listicle   "5 things about X"         │
                   │  ├── Storytime  "The story nobody told"     │
                   │  ├── Comparison "X vs Y — who wins?"       │
                   │  ├── Myth-bust  "3 myths about X debunked" │
                   │  └── News-flash "BREAKING: what this means"│
                   │                                            │
                   │  Each script has: hook · beats · CTA ·     │
                   │  format · duration · hashtags · score       │
                   └────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  output/                       │
              │  ├── veloci_trends_*.json      │
              │  ├── veloci_trends_*.csv       │
              │  ├── scripts_ranked_*.json     │
              │  └── scripts_ranked_*.csv      │
              └───────────────────────────────┘
```

---

## Scoring explained

Each trend gets a **composite score** from 0 → 1, then bucketed into a tier:

| Tier | Score | What it means | What you should do |
|------|-------|---------------|-------------------|
| 🟢 **early** | 0.70–1.00 | You're 12–48h ahead of mainstream | Post in the next 2–6 hours |
| 🟡 **emerging** | 0.50–0.70 | Window is open, closing fast | Post within 24 hours |
| 🟠 **trending** | 0.35–0.50 | Viable but saturating | Proceed with caution |
| 🔴 **saturated** | < 0.35 | Everyone's already covered it | Hard skip |

The velocity score is the most critical signal — we care about **rate of acceleration**, not current popularity. A rising post with 200 upvotes and 40/min velocity beats a hot post with 2000 upvotes and 3/min velocity every time.

---

## Directory structure

```
veloci/
├── main.py                       ← Entry point + CLI + APScheduler
├── config.py                     ← All settings, niches, weights, API keys
├── requirements.txt
├── .env.example                  ← Copy → .env, fill your keys
│
├── scrapers/
│   ├── base.py                   ← RawSignal schema + BaseScraper
│   ├── reddit_scraper.py         ← PRAW (rising + hot + high-ratio new)
│   ├── youtube_scraper.py        ← YouTube Data API v3 + autocomplete
│   ├── google_trends_scraper.py  ← pytrends (realtime + related rising)
│   ├── twitter_scraper.py        ← Tweepy v2 (velocity-aware)
│   ├── news_scraper.py           ← RSS + NewsAPI + GDELT
│   └── instagram_scraper.py      ← Apify (proxy-based, ToS-safe)
│
├── pipeline/
│   ├── nlp_processor.py          ← Embed → DBSCAN → TF-IDF → VADER
│   ├── ranker.py                 ← Composite scoring + tier classification
│   ├── aggregator.py             ← Orchestrates scrapers → NLP → rank
│   └── script_generator.py       ← Stage 02: 8 script angles, full export
│
├── storage/
│   └── database.py               ← Async SQLite (trends + signals + perf)
│
└── output/                       ← Generated trends + scripts (gitignored)
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/yourusername/veloci.git
cd veloci

pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m nltk.downloader stopwords punkt
playwright install chromium
```

### 2. Configure API keys

All keys have generous free tiers — this whole system runs at **$0/month**.

```bash
cp .env.example .env
```

Then fill `.env`:

```env
REDDIT_CLIENT_ID=your_id          # reddit.com/prefs/apps → script app
REDDIT_CLIENT_SECRET=your_secret
REDDIT_USER_AGENT=veloci-bot/1.0 by u/yourusername

YOUTUBE_API_KEY=your_key          # console.cloud.google.com → YouTube Data API v3

TWITTER_BEARER_TOKEN=your_token   # developer.twitter.com → bearer token

NEWS_API_KEY=your_key             # newsapi.org → free (100 req/day)

APIFY_TOKEN=your_token            # console.apify.com → for Instagram (optional)
```

> Google Trends, GDELT, and TikTok need **no keys** — they just work.

---

## Running

```bash
# Check that all scrapers are alive
python main.py --health

# Run once — see what's trending right now
python main.py --once

# Run once for a specific niche
python main.py --once --niche tech_ai

# Export trends to JSON (Stage 01 output)
python main.py --export trends.json --niche finance

# Export trends + CSV to a directory
python main.py --output ./output --niche entertainment

# Generate video scripts for all niches (Stages 01 + 02 combined)
python main.py --scripts ./output

# Generate scripts for one niche, 4 scripts per trend
python main.py --scripts ./output --niche tech_ai --scripts-per-trend 4

# Run continuously — scrapes every 30 minutes, no babysitting needed
python main.py

# Scheduled run for one niche only
python main.py --niche finance
```

---

## Output format

### Trend (Stage 01)

```json
{
  "niche": "tech_ai",
  "generated_at": "2025-06-30T09:00:00Z",
  "trends": [
    {
      "cluster_id": "a3f9b2c1",
      "topic": "OpenAI GPT-5 silent rollout",
      "keywords": ["GPT-5", "OpenAI", "model release", "silent launch"],
      "entities": ["OpenAI", "Sam Altman", "GPT-5"],
      "platforms": ["reddit_rising", "google_trends_rising", "twitter"],
      "composite_score": 0.847,
      "velocity_score": 0.91,
      "cross_platform_score": 0.88,
      "novelty_score": 0.95,
      "sentiment_score": 0.71,
      "tier": "early",
      "content_angles": [
        "Broad: What is GPT-5 and why does it matter today?",
        "Deep-dive: What OpenAI didn't say in the release notes",
        "Reaction: My honest take after testing GPT-5 for 3 hours",
        "Data: The benchmark numbers that should scare Google"
      ]
    }
  ]
}
```

### Script (Stage 02)

```json
{
  "script_id": "d4e8f1a2",
  "trend_topic": "OpenAI GPT-5 silent rollout",
  "angle": "hot_take",
  "hook": "OpenAI just quietly dropped something massive and nobody noticed.",
  "body_beats": [
    "Here's what actually changed...",
    "This is the part that should worry you...",
    "Here's what I'm doing about it..."
  ],
  "cta": "Follow for more takes before they're mainstream.",
  "format": "talking_head",
  "duration": "45-60s",
  "platform": "instagram_reels",
  "hashtags": ["#OpenAI", "#GPT5", "#AINews", "#TechExplained"],
  "script_score": 0.89
}
```

---

## Niche × Channel matrix

The system is pre-configured for **3 niches × 4 channel angles = 12 channels**. Same trend, 4 different scripts. Platform fingerprinting defeated through audio + visual variation. Each channel builds a distinct audience — you're not competing with yourself.

| Niche | Channel A | Channel B | Channel C | Channel D |
|-------|-----------|-----------|-----------|-----------|
| `tech_ai` | Broad explainer | Deep-dive analysis | Hot take / reaction | Stats & data |
| `finance` | Market overview | Deep fundamentals | Reaction to news | Charts & numbers |
| `entertainment` | What happened | Behind the scenes | My honest opinion | Record-breaking data |

---

## API costs breakdown

| Source | Free limit | VELOCI usage/cycle | Monthly cost |
|--------|-----------|-------------------|--------------|
| Reddit PRAW | 100 req/min | ~20 req | **$0** |
| YouTube Data API | 10,000 units/day | ~1,500 units × 48 cycles | **$0** |
| Twitter/X | 500K tweets/month | ~500/cycle × 48 cycles/day | **$0** |
| NewsAPI | 100 req/day | 6 req/cycle × 2 cycles max | **$0** |
| Google Trends | Unofficial, be polite | 5 req/cycle w/ 2.5s delay | **$0** |
| GDELT | Open, no limit | 4 req/cycle | **$0** |
| Instagram/Apify | ~5K reels/mo free credits | Optional, graceful fallback | **~$0–5** |
| **Total** | | | **≈ $0/month** |

---

## Why these design choices?

**DBSCAN over K-means** — K-means needs K upfront. We don't know how many clusters will emerge from a given cycle. DBSCAN discovers them organically and marks true outliers as noise rather than forcing them into the wrong group.

**RISING not HOT** — Reddit's rising sort shows *velocity right now*. Hot shows *what already won*. The delta between them is your lead time.

**GDELT** — Scrapes 100+ languages, 250+ countries, near-real-time. A product launch in Korea or a regulation in Brazil appears in GDELT hours before it trends in English social media. For international niches this is the unfair edge nobody talks about.

**Google Trends RELATED RISING** — Breakout queries (5000%+ growth) are the single best predictor of what people will be searching for on YouTube in 24–72 hours. This is the upstream signal that most trend tools don't even know to look for.

**No LLM in Stage 02** — The script generator uses an intelligent template engine seeded with actual trend data (entities, keywords, sentiment, platform context). It's fast, deterministic, free, and produces scripts that are already 80% of the way there. Plug in an LLM call to `_generate_body()` if you want the other 20%.

**Instagram by design, not by accident** — IG has no public trend API and its private API violates ToS. But IG trends lag 2–5 days behind TikTok/Reddit anyway. VELOCI predicts IG trends *before they exist on IG* — which is the entire point.

---

## Known limitations (being honest)

1. **TikTok will occasionally break** — they actively change their DOM. The Playwright scraper uses CSS selectors + XHR intercept as dual fallbacks. The XHR path is more stable. Expect to update selectors every few months.

2. **Twitter free tier is real** — 500K tweets/month sounds like a lot. At 100 results × 5 queries × 48 cycles/day you're at 240K/day. Scale down queries or move to Basic ($100/mo) if you hit the wall.

3. **Google Trends 429s** — pytrends is unofficial. The 2.5s inter-request delay is conservative and should be fine. If you see 429s, bump `INTER_REQUEST_DELAY` in `config.py`.

4. **Embedding on cold start is slow** — `all-MiniLM-L6-v2` downloads ~85MB on first run and loads into RAM (~200MB). Subsequent runs are fast. On a potato machine, give it 30–60s on first cycle.

---

## Roadmap

- [x] Stage 01: Multi-source trend intelligence
- [x] Stage 02: Template-based script generation (8 angles)
- [ ] Stage 03: Multimodal engagement predictor (θ gate)
- [ ] Stage 04: Contextual bandit RL publish scheduler
- [ ] Stage 05: Auto-publish layer (Instagram Reels, YouTube Shorts)
- [ ] Stage 06: Feedback learning loop (views → reward signal)
- [ ] Stage 07: Analytics dashboard

---

## Contributing

If you're reading this and thinking *I know how to make Stage 03 better* — open an issue. The engagement predictor is the hardest part and the most interesting. Would genuinely love a collaborator who's done multimodal representation learning.

Otherwise: fork it, break it, improve it. That's the spirit.

---

<div align="center">

Built as part of autonomous UGC systems research · Sem 6, 2026

*"The best time to post was yesterday. The second best time is right now — if you know what to post."*

</div>
