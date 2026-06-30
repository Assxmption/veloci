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
- GDELT covers 100+ languages — a launch in Korea surfaces in English feeds hours before anyone in the West knows it happened

**Lead time is the only moat in content creation.** VELOCI is that moat.

---

## What's built (right now)

```
Stage 01: Trend Intelligence     ██████████  DONE
Stage 02: Script Generation      ██████████  DONE
Stage 03: Engagement Predictor   ██████░░░░  SPEC + EVAL STUB DONE — full impl next
Stage 04: RL Publish Scheduler   ██░░░░░░░░  REWARD SIMULATION DONE — full impl next
Stage 05: Auto-Publish Layer     ░░░░░░░░░░  PLANNED
Stage 06: Feedback Loop          ░░░░░░░░░░  PLANNED
Stage 07: Analytics Dashboard    ░░░░░░░░░░  PLANNED
```

---

## The pipeline (how it actually works)

```
                    ┌──────────────────────────────────────┐
                    │          VELOCI ENGINE v2.0           │
                    └──────────────────────────────────────┘

  INPUT SOURCES                   NLP CORE                    OUTPUT
  ─────────────                   ────────                    ──────

  Reddit RISING   ──┐
  YouTube Trends  ──┤   ┌──────────────────────────┐
  Google Trends   ──┤   │ 1. Clean & normalize      │   ┌──────────────────┐
  Twitter/X       ──┼──▶│ 2. Semantic embed 384-d   │──▶│  TrendCluster[]  │
  NewsAPI + RSS   ──┤   │ 3. DBSCAN cluster         │   │  - topic         │
  GDELT           ──┤   │ 4. TF-IDF keywords        │   │  - score 0-1     │
  Instagram/Apify ──┘   │ 5. NER entities           │   │  - tier (early→) │
         ↑             │ 6. VADER sentiment          │   │  - platforms[]   │
   [rate_limiter]       └──────────────────────────┘   │  - angles[]      │
   token bucket +                                        └──────────────────┘
   circuit breaker                                                │
                                ┌─────────────────────────────────┘
                                ▼
                    ┌─────────────────────────────────┐
                    │   RANKER                         │
                    │   velocity        ×0.35          │   Composite score =
                    │   cross-platform  ×0.25          │   weighted sum of
                    │   novelty         ×0.20          │   all five signals
                    │   sentiment       ×0.10          │
                    │   engagement      ×0.10          │
                    └─────────────────────────────────┘
                                │
                                ▼
                    ┌──────────────────────────────────────────┐
                    │       SCRIPT GENERATOR  (Stage 02)        │
                    │                                          │
                    │  Per trend × up to 8 angles:             │
                    │  ├── Explainer   "What is X and why now" │
                    │  ├── Hot-take    "My controversial take"  │
                    │  ├── Tutorial    "How to use X right now" │
                    │  ├── Listicle   "5 things about X"       │
                    │  ├── Storytime  "The story nobody told"   │
                    │  ├── Comparison "X vs Y — who wins?"     │
                    │  ├── Myth-bust  "3 myths debunked"       │
                    │  └── News-flash "BREAKING: what it means"│
                    │                                          │
                    │  hook · beats · CTA · format ·           │
                    │  duration · hashtags · script score       │
                    └──────────────────────────────────────────┘
                                │
                                ▼
                    ┌──────────────────────────────┐
                    │  output/                      │
                    │  ├── veloci_trends_*.json     │
                    │  ├── veloci_trends_*.csv      │
                    │  ├── scripts_ranked_*.json    │
                    │  └── scripts_ranked_*.csv     │
                    └──────────────────────────────┘
```

---

## Scoring explained

Each trend gets a **composite score** from 0 → 1, then bucketed into a tier:

| Tier | Score | What it means | What you should do |
|------|-------|---------------|--------------------|
| 🟢 **early** | 0.70–1.00 | You're 12–48h ahead of mainstream | Post in the next 2–6 hours |
| 🟡 **emerging** | 0.50–0.70 | Window is open, closing fast | Post within 24 hours |
| 🟠 **trending** | 0.35–0.50 | Viable but saturating | Proceed with caution |
| 🔴 **saturated** | < 0.35 | Everyone's already covered it | Hard skip |

The velocity score carries the most weight (×0.35) — we care about **rate of acceleration**, not current popularity. A rising post with 200 upvotes and 40/min velocity beats a hot post with 2,000 upvotes and 3/min velocity every single time.

---

## Directory structure

```
veloci/
├── main.py                        ← Entry point + CLI + APScheduler
├── config.py                      ← All settings, niches, weights, API keys
├── requirements.txt
├── .env.example                   ← Copy → .env, fill your keys
├── veloci_evaluation.py           ← Evaluation suite: scoring tests + Stage 03/04 stubs
│
├── scrapers/
│   ├── base.py                    ← RawSignal schema + BaseScraper
│   ├── reddit_scraper.py          ← PRAW (rising + hot + high-ratio new)
│   ├── youtube_scraper.py         ← YouTube Data API v3 + autocomplete
│   ├── google_trends_scraper.py   ← pytrends (realtime + related rising)
│   ├── twitter_scraper.py         ← Tweepy v2 (velocity-aware)
│   ├── news_scraper.py            ← RSS + NewsAPI + GDELT
│   └── instagram_scraper.py       ← Apify (proxy-based, ToS-safe)
│
├── pipeline/
│   ├── nlp_processor.py           ← Embed → DBSCAN → TF-IDF → VADER
│   ├── ranker.py                  ← Composite scoring + tier classification
│   ├── rate_limiter.py            ← Token bucket + circuit breaker (per-platform)
│   ├── aggregator.py              ← Orchestrates scrapers → NLP → rank
│   └── script_generator.py        ← Stage 02: 8 script angles, full export
│
├── storage/
│   └── database.py                ← Async SQLite (trends + signals + perf)
│
└── output/                        ← Generated trends + scripts (gitignored)
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/Assxmption/veloci.git
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

> Google Trends and GDELT need **no keys** — they just work.

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
|--------|------------|--------------------|--------------|
| Reddit PRAW | 60 req/min | ~20 req | **$0** |
| YouTube Data API | 10,000 units/day | ~1,500 units × 48 cycles | **$0** |
| Twitter/X | 500K tweets/month | ~500/cycle × 48 cycles/day | **$0** |
| NewsAPI | 100 req/day | 6 req/cycle × 2 cycles max | **$0** |
| Google Trends | Unofficial, ~30 req/hr | 5 req/cycle w/ 2.5s delay | **$0** |
| GDELT | Open, no limit | 4 req/cycle | **$0** |
| Instagram/Apify | ~5K reels/mo free credits | Optional, graceful fallback | **~$0–5** |
| **Total** | | | **≈ $0/month** |

---

## Why these design choices?

**DBSCAN over K-means** — K-means needs K upfront. We don't know how many clusters will emerge from a given cycle. DBSCAN discovers them organically and marks true outliers as noise rather than forcing them into the wrong group.

**RISING not HOT** — Reddit's rising sort shows *velocity right now*. Hot shows *what already won*. The delta between them is your lead time.

**GDELT** — Scrapes 100+ languages, 250+ countries, near-real-time. A product launch in Korea or a regulation in Brazil appears in GDELT hours before it trends in English social media. For international niches this is the unfair edge nobody talks about.

**Google Trends RELATED RISING** — Breakout queries (5000%+ growth) are the single best predictor of what people will be searching for on YouTube in 24–72 hours. This is the upstream signal that most trend tools don't even know to look for.

**Token bucket + circuit breaker** — Every platform scraper goes through `rate_limiter.py`. Token buckets enforce free-tier API budgets per platform. Circuit breakers trip after 3 consecutive failures and enter a 5-minute cooldown — so one broken platform can't stall the whole cycle.

**No LLM in Stage 02** — The script generator uses an intelligent template engine seeded with actual trend data (entities, keywords, sentiment, platform context). It's fast, deterministic, free, and produces scripts that are already 80% of the way there. Plug in an LLM call to `_generate_body()` if you want the other 20%.

**Instagram by design, not by accident** — IG has no public trend API and its private API violates ToS. But IG trends lag 2–5 days behind Reddit/YouTube anyway. VELOCI predicts IG trends *before they exist on IG* — which is the entire point.

---

## Stage 03 — what's coming

The engagement predictor is specced in `VELOCI_THESIS_DOCUMENTATION.md` and **draft-evaluated** in `veloci_evaluation.py`. The architecture:

```
E = f(video_frames, audio, caption, metadata)
     ViT-base + wav2vec2 + MiniLM → CrossModalAttentionFusion
     → NAWP + ECR prediction heads
     → E ≥ θ: publish | E < θ: regenerate
```

Where `θ` (the publish gate) is adaptive — it drifts with the top quartile of recent scores so the bar rises as content quality improves.

`veloci_evaluation.py` contains a **Ridge regression surrogate** that simulates the full multimodal predictor against unimodal baselines (visual-only, audio-only, text-only), reporting MAE on NAWP/ECR and F1 on the viral gate. Target thresholds from the spec:

| Metric | Target | Status |
|--------|--------|--------|
| MAE (NAWP) | < 0.08 | Evaluated in Section 5 |
| MAE (ECR) | < 0.10 | Evaluated in Section 5 |
| F1 (Viral gate) | > 0.75 | Evaluated in Section 5 |

The Stage 04 RL scheduler reward simulation is also in there — 500 episodes of epsilon-greedy bandit learning across 48 publish slots, with convergence analysis.

---

## Evaluation suite

`veloci_evaluation.py` is a standalone draft scorer — no live scraping required. It validates the entire pipeline analytically.

```bash
pip install numpy pandas scikit-learn scipy sentence-transformers vaderSentiment
python veloci_evaluation.py
```

What it runs:

| Section | What it tests |
|---------|---------------|
| 1 — Scoring unit tests | Velocity, cross-platform, composite bounds, tier classification (7 assertions) |
| 2 — DBSCAN quality | Silhouette score + Davies-Bouldin Index on real sentence embeddings |
| 3 — Trend ranking | 7 synthetic trends scored + ranked, weight sensitivity analysis |
| 4 — Stage 03 stub | Multimodal engagement predictor: Ridge surrogate vs. unimodal baselines, MAE + F1 |
| 5 — Stage 04 stub | RL contextual bandit: 500 episodes, Q-convergence, reward uplift vs. static heuristic |
| 6 — Script scoring | 8 content angles scored across 2 topics, ranked by composite |
| Summary | Pass rates, mean scores, cycle times — all in one table |

> **Note:** This is a *draft evaluation* — the engagement predictor uses a linear surrogate in place of the full ViT + wav2vec2 model, and the RL scheduler uses a simplified bandit in place of the full LSTM-Q network. Both are faithful stand-ins for validating the scoring logic and target thresholds before the full implementation.

---

## Known limitations (being honest)

1. **Instagram Apify can hit credit limits** — The free tier gives ~$5/month in credits (~5K reels). The scraper falls back gracefully when the budget runs out; the rest of the pipeline keeps running.

2. **Twitter free tier is real** — 500K tweets/month sounds like a lot. At 100 results × 5 queries × 48 cycles/day you're at 240K/day. Scale down queries or move to Basic ($100/mo) if you hit the wall.

3. **Google Trends 429s** — pytrends is unofficial. The 2.5s inter-request delay is conservative and should be fine. If you see 429s, bump `INTER_REQUEST_DELAY` in `config.py`.

4. **Embedding on cold start is slow** — `all-MiniLM-L6-v2` downloads ~85MB on first run and loads into RAM (~200MB). Subsequent runs are fast. On a potato machine, give it 30–60s on first cycle.

---

## Roadmap

- [x] Stage 01: Multi-source trend intelligence (8 platforms)
- [x] Stage 02: Template-based script generation (8 angles)
- [~] Stage 03: Multimodal engagement predictor — spec + draft evaluation done (`veloci_evaluation.py` §5), full ViT+wav2vec2 impl next
- [~] Stage 04: RL contextual bandit scheduler — reward simulation done (`veloci_evaluation.py` §6), full LSTM-Q impl next
- [ ] Stage 05: Auto-publish layer (Instagram Reels, YouTube Shorts)
- [ ] Stage 06: Feedback learning loop (views → reward signal)
- [ ] Stage 07: Analytics dashboard

---

## Contributing

If you're reading this and thinking *I know how to make Stage 03 better* — open an issue. The engagement predictor is the hardest part and the most interesting. Would genuinely love a collaborator who's done multimodal representation learning or cross-modal attention fusion.

Otherwise: fork it, break it, improve it. That's the spirit.

---

<div align="center">

Built as part of autonomous UGC systems research · Sem 6, 2026

*"The best time to post was yesterday. The second best time is right now — if you know what to post."*

</div>
